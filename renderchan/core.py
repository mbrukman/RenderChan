__author__ = 'Konstantin Dmitriev'

import sys
from renderchan.file import RenderChanFile
from renderchan.project import RenderChanProjectManager
from renderchan.module import RenderChanModuleManager
from renderchan.utils import mkdirs
from renderchan.utils import float_trunc
from renderchan.utils import sync
from renderchan.utils import switchProfile
from puliclient import Task, Graph
import os, time

class RenderChan():
    def __init__(self):

        self.puliServer = ""
        self.puliPort = 8004

        print "RenderChan initialized."
        self.projects = RenderChanProjectManager()
        self.modules = RenderChanModuleManager()
        self.modules.loadAll()

        self.loadedFiles = {}

        self.graph = Graph( 'RenderChan graph', poolName="default" )
        # == taskgroups bug / commented ==
        # The following are the special taskgroups used for managing stereo rendering
        #self.taskgroupLeft = None
        #self.taskgroupRight = None

        # FIXME: The childTask is a dirty workaround, which we need because of broken taskgroups functionality (search for "taskgroups bug" string to get the commented code)
        self.childTask = None

    def setHost(self, host):
        self.puliServer=host

    def setPort(self, port):
        self.puliPort=port

    def submit(self, taskfile, useDispatcher=True, dependenciesOnly=False, allocateOnly=False, stereo=""):

        """

        :type taskfile: RenderChanFile
        """

        if stereo in ("vertical","v","horizontal","h"):

            # Left eye graph
            self.projects.setStereoMode("left")
            self.addToGraph(taskfile, dependenciesOnly, allocateOnly)
            input_left = taskfile.getProfileRenderPath()

            # Right eye graph
            self.projects.setStereoMode("right")
            self.childTask = taskfile.taskPost
            self.addToGraph(taskfile, dependenciesOnly, allocateOnly)
            input_right = taskfile.getProfileRenderPath()

            # Stitching altogether
            name = taskfile.getPath()
            runner = "renderchan.puli.RenderChanStereoPostRunner"
            decomposer = "renderchan.puli.RenderChanNullDecomposer"
            params={}
            params["input_left"]=input_left
            params["input_right"]=input_right
            params["output"] = os.path.splitext(taskfile.getRenderPath())[0]+"-stereo"
            if stereo in ("vertical","v"):
                params["stereo_mode"] = "vertical"
                params["output"]+="-v"
            else:
                params["stereo_mode"] = "horizontal"
                params["output"]+="-h"
            params["output"]+=".avi"
            stereoTask = self.graph.addNewTask( name="StereoPost: "+name, runner=runner, arguments=params, decomposer=decomposer )

            # Dummy task
            #decomposer = "puliclient.contrib.generic.GenericDecomposer"
            #params={ "cmd":"echo", "start":1, "end":1, "packetSize":1, "prod":"test", "shot":"test" }
            #dummyTask = self.graph.addNewTask( name="StereoDummy", arguments=params, decomposer=decomposer )

            # == taskgroups bug / commented ==
            #self.graph.addEdges( [(self.taskgroupLeft, self.taskgroupRight)] )
            #self.graph.addEdges( [(self.taskgroupRight, stereoTask)] )
            #self.graph.addChain( [self.taskgroupLeft, dummyTask, self.taskgroupRight, stereoTask] )
            if taskfile.taskPost!=None:
                self.graph.addEdges( [(taskfile.taskPost, stereoTask)] )

            last_task = stereoTask

        else:
            if stereo in ("left","l"):
                self.projects.setStereoMode("left")
            elif stereo in ("right","r"):
                self.projects.setStereoMode("right")
            self.addToGraph(taskfile, dependenciesOnly, allocateOnly)

            last_task = taskfile.taskPost

        if last_task==None:
            # Profile syncronization
            #runner = "renderchan.puli.RenderChanProfileSyncRunner"
            #decomposer = "renderchan.puli.RenderChanNullDecomposer"
            for project_path in self.projects.list.keys():
                #params={}
                #params["projects"] = project_path
                #params["profile"] = self.projects.active.activeProfile
                #sync_task = self.graph.addNewTask( name="Sync: "+project_path, runner=runner, arguments=params, decomposer=decomposer )
                #if last_task!=None:
                #    self.graph.addEdges( [(last_task, sync_task)] )
                print "Switching profile..."
                t=switchProfile(project_path, self.projects.active.getProfileDirName())
                t.unlock()

        # Finally submit the graph to Puli

        if self.puliServer=="":
            server="127.0.0.1"
            # TODO: If no server address given, then try to run our own dispatcher
            # ...
        else:
            server=self.puliServer

        if useDispatcher:
            # Submit to dispatcher host
            self.graph.submit(server, self.puliPort)
        else:
            # Local rendering
            self.graph.execute()

    def addToGraph(self, taskfile, dependenciesOnly=False, allocateOnly=False):
        """

        :type taskfile: RenderChanFile
        """

        for path in self.loadedFiles.keys():
            self.loadedFiles[path].isDirty=None
        #self.loadedFiles={}

        # == taskgroups bug / commented ==
        # Prepare taskgroups if we do stereo rendering
        #if self.projects.active.getConfig("stereo")=="left":
        #    self.taskgroupLeft = self.graph.addNewTaskGroup( name="TG Left: "+taskfile.getPath() )
        #elif self.projects.active.getConfig("stereo")=="right":
        #    self.taskgroupRight = self.graph.addNewTaskGroup( name="TG Right: "+taskfile.getPath() )


        if allocateOnly and dependenciesOnly:

            if os.path.exists(taskfile.getRenderPath()):
                self.parseDirectDependency(taskfile, None)
            else:
                taskfile.endFrame = taskfile.startFrame + 2
                self.parseRenderDependency(taskfile, allocateOnly)

        elif dependenciesOnly:

            self.parseDirectDependency(taskfile, None)

        elif allocateOnly:

            if os.path.exists(taskfile.getRenderPath()):
                print "File is already allocated."
                sys.exit(0)
            taskfile.dependencies=[]
            taskfile.endFrame = taskfile.startFrame + 2
            self.parseRenderDependency(taskfile, allocateOnly)

        else:

            self.parseRenderDependency(taskfile, allocateOnly)


        self.childTask = None


    def parseRenderDependency(self, taskfile, allocateOnly):
        """

        :type taskfile: RenderChanFile
        """

        # TODO: Re-implement this function in the same way as __not_used__syncProfileData() ?

        isDirty = False

        # First, let's ensure, that we are in sync with profile data
        #checkTime=None
        #if os.path.exists(taskfile.getProfileRenderPath()+".sync"):
        #    checkFile=os.path.join(taskfile.getProjectRoot(),"render","project.conf","profile.conf")
        #    checkTime=float_trunc(os.path.getmtime(checkFile),1)
        #if os.path.exists(taskfile.getProfileRenderPath()):
        #
        #    source=taskfile.getProfileRenderPath()
        #    dest=taskfile.getRenderPath()
        #    sync(source,dest,checkTime)
        #
        #    source=os.path.splitext(taskfile.getProfileRenderPath())[0]+"-alpha."+taskfile.getFormat()
        #    dest=os.path.splitext(taskfile.getRenderPath())[0]+"-alpha."+taskfile.getFormat()
        #    sync(source,dest,checkTime)
        #
        #else:
        #    isDirty = True


        if not os.path.exists(taskfile.getProfileRenderPath()):
            # If no rendering exists, then obviously rendering is required
            isDirty = True
            compareTime = None
        else:
            # Otherwise we have to check against the time of the last rendering
            compareTime = float_trunc(os.path.getmtime(taskfile.getProfileRenderPath()),1)

        # Get "dirty" status for the target file and all dependent tasks, submitted as dependencies
        (isDirtyValue,tasklist, maxTime)=self.parseDirectDependency(taskfile, compareTime)

        if isDirtyValue:
            isDirty = True

        # If rendering is requested
        if isDirty:

            # Puli part here

            name = taskfile.localPath

            graph_destination = self.graph
            # == taskgroups bug / commented ==
            #if self.projects.active.getConfig("stereo")=="left":
            #    graph_destination = self.taskgroupLeft
            #    name+=" (L)"
            #elif self.projects.active.getConfig("stereo")=="right":
            #    graph_destination = self.taskgroupRight
            #    name+=" (R)"
            #else:
            #    graph_destination = self.graph

            runner = "renderchan.puli.RenderChanRunner"
            decomposer = "renderchan.puli.RenderChanDecomposer"

            params = taskfile.getParams()
            params["projects"]=[]
            for project in self.projects.list.keys():
                params["projects"].append(project)
            # Max time is a
            if allocateOnly:
                # Make sure this file will be re-rendered next time
                params["maxTime"]=taskfile.mtime-1000
            else:
                params["maxTime"]=maxTime

            # Make sure we have all directories created
            mkdirs(os.path.dirname(params["profile_output"]))
            mkdirs(os.path.dirname(params["output"]))

            # Add rendering task to the graph
            taskfile.taskRender=graph_destination.addNewTask( name="Render: "+name, runner=runner, arguments=params, decomposer=decomposer )


            # Now we will add a task which composes results and places it into valid destination

            # Add rendering task to the graph
            runner = "renderchan.puli.RenderChanPostRunner"
            decomposer = "renderchan.puli.RenderChanNullDecomposer"
            taskfile.taskPost=graph_destination.addNewTask( name="Post: "+name, runner=runner, arguments=params, decomposer=decomposer,
                                       maxNbCores=taskfile.module.conf["maxNbCores"] )

            self.graph.addEdges( [(taskfile.taskRender, taskfile.taskPost)] )

            # Add edges for dependent tasks
            for task in tasklist:
                self.graph.addEdges( [(task, taskfile.taskRender)] )

            if self.childTask!=None:
                self.graph.addEdges( [(self.childTask, taskfile.taskRender)] )

        # Mark this file as already parsed and thus its "dirty" value is known
        taskfile.isDirty=isDirty

        return isDirty


    def parseDirectDependency(self, taskfile, compareTime):
        """

        :type taskfile: RenderChanFile
        """

        tasklist=[]

        self.loadedFiles[taskfile.getPath()]=taskfile

        if taskfile.isFrozen():
            return (False, [], 0)

        if taskfile.project!=None and taskfile.module!=None:
            self.loadedFiles[taskfile.getRenderPath()]=taskfile

        deps = taskfile.getDependencies()

        # maxTime is the maximum of modification times for all direct dependencies.
        # It allows to compare with already rendered pieces and continue rendering
        # if they are rendered AFTER the maxTime.
        #
        # But, if we have at least one INDIRECT dependency (i.e. render task) and it is submitted
        # for rendering, then we can't compare with maxTime (because dependency will be rendered
        # and thus rendering should take place no matter what).
        maxTime = taskfile.getTime()

        taskfile.pending=True  # we need this to avoid circular dependencies

        isDirty=False
        for path in deps:
            if path in self.loadedFiles.keys():
                dependency = self.loadedFiles[path]
                if dependency.pending:
                    # Avoid circular dependencies
                    print "Warning: Circular dependency detected for %s. Skipping." % (path)
                    continue
            else:
                dependency = RenderChanFile(path, self.modules, self.projects)
                if not os.path.exists(dependency.getPath()):
                    print "   Skipping file %s..." % path
                    continue

            # Check if this is a rendering dependency
            if path != dependency.getPath():
                # We have a new task to render
                if dependency.isDirty==None:
                    if dependency.module!=None:
                        dep_isDirty = self.parseRenderDependency(dependency, allocateOnly=False)
                    else:
                        raise Exception("No module to render file")
                else:
                    # The dependency was already submitted to graph
                    dep_isDirty = dependency.isDirty

                if dep_isDirty:
                    # Let's return submitted task into tasklist
                    if not dependency.taskPost in tasklist:
                        tasklist.append(dependency.taskPost)
                    # Increase maxTime, because re-rendering of dependency will take place
                    maxTime=time.time()
                    isDirty = True
                else:
                    # If no rendering requested, we still have to check if rendering result
                    # is newer than compareTime

                    #if os.path.exists(dependency.getRenderPath()):  -- file is obviously exists, because isDirty==0
                    timestamp=float_trunc(os.path.getmtime(dependency.getProfileRenderPath()),1)

                    if compareTime is None:
                        isDirty = True
                    elif timestamp > compareTime:
                        isDirty = True
                    if timestamp>maxTime:
                        maxTime=timestamp

            else:
                # No, this is an ordinary dependency
                    (dep_isDirty, dep_tasklist, dep_maxTime) = self.parseDirectDependency(dependency, compareTime)
                    if dep_isDirty:
                        isDirty=True
                    if dep_maxTime>maxTime:
                        maxTime=dep_maxTime
                    for task in dep_tasklist:
                        if not task in tasklist:
                            tasklist.append(task)

        if not isDirty:
            timestamp = float_trunc(taskfile.getTime(), 1)
            if compareTime is None:
                isDirty = True
            elif timestamp > compareTime:
                isDirty = True
            if timestamp>maxTime:
                maxTime=timestamp

        taskfile.pending=False

        return (isDirty, list(tasklist), maxTime)

    def __not_used__syncProfileData(self, renderpath):

        if renderpath in self.loadedFiles.keys():
            taskfile = self.loadedFiles[renderpath]
            if taskfile.pending:
                # Avoid circular dependencies
                print "Warning: Circular dependency detected for %s. Skipping." % (renderpath)
                return
        else:
            taskfile = RenderChanFile(renderpath, self.modules, self.projects)
            if not os.path.exists(taskfile.getPath()):
                print "   No source file for %s. Skipping." % renderpath
                return
            self.loadedFiles[taskfile.getPath()]=taskfile
            taskfile.pending=True  # we need this to avoid circular dependencies
            if taskfile.project!=None and taskfile.module!=None:
                self.loadedFiles[taskfile.getRenderPath()]=taskfile

        deps = taskfile.getDependencies()
        for path in deps:
            self.syncProfileData(path)

        if renderpath != taskfile.getPath():
            # TODO: Change parseRenderDependency() in the same way?
            checkFile=os.path.join(taskfile.getProjectRoot(),"render","project.conf","profile.conf")
            checkTime=float_trunc(os.path.getmtime(checkFile),1)

            source=taskfile.getProfileRenderPath()
            dest=taskfile.getRenderPath()
            sync(source,dest,checkTime)

            source=os.path.splitext(taskfile.getProfileRenderPath())[0]+"-alpha."+taskfile.getFormat()
            dest=os.path.splitext(taskfile.getRenderPath())[0]+"-alpha."+taskfile.getFormat()
            sync(source,dest,checkTime)

        taskfile.pending=False

