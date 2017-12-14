

__author__ = 'Konstantin Dmitriev'

from renderchan.module import RenderChanModule
from renderchan.utils import which, is_true_string
from distutils.version import StrictVersion
import subprocess
import tempfile
import os
import re
import random
from zipfile import ZipFile
from xml.etree import ElementTree

class RenderChanPencil2dModule(RenderChanModule):
    def __init__(self):
        RenderChanModule.__init__(self)
        if os.name == 'nt':
            self.conf['binary']=os.path.join(os.path.dirname(__file__),"..\\..\\..\\pencil\\pencil2d.exe")
        else:
            self.conf['binary']="pencil2d"
        self.conf["packetSize"]=0
        # Extra params
        self.extraParams["transparency"]="0"
        self.extraParams["width"]="-1"
        self.extraParams["height"]="-1"
        self.extraParams["startFrame"]="1"
        self.extraParams["endFrame"]="last"

        # The CLI features depend on the version
        with tempfile.TemporaryDirectory() as tmpPath:
            # The exporting of a fake file is a workaround for older versions which just start the program when passed only -v
            versionProc = subprocess.run(["pencil2d", tmpPath, "-v", "--export-sequence", "test"], stdout=subprocess.PIPE)
        if versionProc.returncode != 0:
            # Some old version which doesn't support the -v flag
            self.version = StrictVersion('0.5.4')
        else:
            # Get the version from stdout. An example of the output: "Pencil2D 0.6.0\n"
            #print(type(versionProc.stdout.rstrip().decode("utf-8").split(" "))
            self.version = StrictVersion(versionProc.stdout.decode("utf-8").rstrip().split(" ")[-1])

    def analyze(self, filename):
        info={ "dependencies":[] }
        if filename.endswith(".pcl"):
            with open(filename, 'r') as f:
                tree = ElementTree.parse(f)
                root = tree.getroot()

                info["dependencies"].extend((os.path.join(filename + ".data", element.get("src")) for element in root.findall(".//*[@src]")))
        else:
            # We don't actually have to do anything here because there are no dependencies and the default values
            # automatically update for changes in the internal width, height, camera etc.
            # This is how we would open it if we needed to
            """with ZipFile(filename) as zipdir:
                with zipdir.open('main.xml') as mainfile:
                    tree = ElementTree.parse(mainfile)
                    root = tree.getroot()"""

        return info

    def getInputFormats(self):
        if self.version >= StrictVersion('0.6.0'):
            return ["pcl", "pclx"]
        else:
            return ["pcl"]

    def getOutputFormats(self):
        if self.version > StrictVersion('0.6.0'):
            return ["png", "jpg", "jpeg", "tif", "tiff", "bmp", "mp4", "avi", "gif", "webm"]
        elif self.version == StrictVersion('0.6.0'):
            return ["png", "jpg", "jpeg", "tif", "tiff", "bmp"]
        else:
            return ["png"]

    def render(self, filename, outputPath, startFrame, endFrame, format, updateCompletion, extraParams={}):
        comp = 0.0
        updateCompletion(comp)

        output = os.path.join(outputPath,"file")
        if not os.path.exists(outputPath):
            os.mkdir(outputPath)

        if self.version > StrictVersion('0.6.0'):
            commandline=[self.conf['binary'], filename, "-o", output, "--width", extraParams['width'], "--height", extraParams['height'], "--start", startFrame, "--end", endFrame]
            if is_true_string(extraParams['transparency']):
                commandline.append("--transparency")
            if extraParams['camera']:
                commandline.extend(["--camera", extraParams['camera']])
        elif self.version == StrictVersion('0.6.0'):
            commandline=[self.conf['binary'], filename, "--export-sequence", output, "--width", extraParams['width'], "--height", extraParams['height']]
            if is_true_string(extraParams['transparency']):
                commandline.append("--transparency")
        else:
            commandline=[self.conf['binary'], filename, "--export-sequence", output]

        print(commandline)
        subprocess.check_call(commandline)

        updateCompletion(1.0)
