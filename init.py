#  -*- coding: latin-1 -*-
###############################################################################
#  #
#  # Copyright (C) 2010-2012, USGS Fort Collins Science Center.
#  # All rights reserved.
#  # Contact: talbertc@usgs.gov
#  #
#  # This file is part of the Software for Assisted Habitat Modeling package
#  # for VisTrails.
#  #
#  # "Redistribution and use in source and binary forms, with or without
#  # modification, are permitted provided that the following conditions are met:
#  #
#  #  - Redistributions of source code must retain the above copyright notice,
#  #    this list of conditions and the following disclaimer.
#  #  - Redistributions in binary form must reproduce the above copyright
#  #    notice, this list of conditions and the following disclaimer in the
#  #    documentation and/or other materials provided with the distribution.
#  #  - Neither the name of the University of Utah nor the names of its
#  #    contributors may be used to endorse or promote products derived from
#  #    this software without specific prior written permission.
#  #
#  # THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
#  # AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
#  # THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
#  # PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
#  # CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
#  # EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
#  # PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
#  # OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
#  # WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
#  # OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
#  # ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."
#  #
#  # Although this program has been used by the U.S. Geological Survey (USGS),
#  # no warranty, expressed or implied, is made by the USGS or the
#  # U.S. Government as to the accuracy and functioning of the program and
#  # related program material nor shall the fact of distribution constitute
#  # any such warranty, and no responsibility is assumed by the USGS
#  # in connection therewith.
#  #
#  # Any use of trade, firm, or product names is for descriptive purposes only
#  # and does not imply endorsement by the U.S. Government.
###############################################################################

import csv
import os
import shutil
import subprocess
import random
import copy
import time

import numpy as np

try:
    from vistrails.core.cache.hasher import sha_hash
    from vistrails.core.modules.vistrails_module import Module, ModuleError, ModuleConnector, ModuleSuspended
    from vistrails.core.modules.basic_modules import File, Directory, Path, new_constant, Constant
    from vistrails.packages.spreadsheet.basic_widgets import SpreadsheetCell, CellLocation
    from vistrails.packages.spreadsheet.spreadsheet_cell import QCellWidget, QCellToolBar
    from vistrails.gui.modules.module_configure import StandardModuleConfigurationWidget
    from vistrails.core.modules.basic_modules import String
    from vistrails.core.packagemanager import get_package_manager
    from vistrails.core.upgradeworkflow import UpgradeWorkflowHandler
    from vistrails.core import system
except ImportError:
    from core import system
    from core.cache.hasher import sha_hash
    from core.modules.vistrails_module import Module, ModuleError, ModuleConnector, ModuleSuspended
    from core.modules.basic_modules import File, Directory, Path, new_constant, Constant
    from packages.spreadsheet.basic_widgets import SpreadsheetCell, CellLocation
    from packages.spreadsheet.spreadsheet_cell import QCellWidget, QCellToolBar
    from core.modules.module_configure import StandardModuleConfigurationWidget
    from core.modules.basic_modules import String
    from core.packagemanager import get_package_manager
    from core.upgradeworkflow import UpgradeWorkflowHandler
    from core import system

from PyQt4 import QtCore, QtGui

from widgets import get_predictor_widget, get_predictor_config

from SelectPredictorsLayers import SelectListDialog
from SelectAndTestFinalModel import SelectAndTestFinalModel

import utils
import GenerateModuleDoc as GenModDoc
#  import our python SAHM Processing files
import pySAHM.FieldDataAggreagateAndWeight as FDAW
import pySAHM.MDSBuilder as MDSB
import pySAHM.MDSBuilder_vector as MDSB_V
import pySAHM.PARC as parc
import pySAHM.RasterFormatConverter as RFC
import pySAHM.runMaxent as MaxentRunner
import pySAHM.utilities as utilities
import pySAHM.SpatialUtilities as SpatialUtilities
from SahmOutputViewer import SAHMModelOutputViewerCell
from SahmSpatialOutputViewer import SAHMSpatialOutputViewerCell
#  from GeneralSpatialViewer import GeneralSpatialViewer

from spatial_modules import BaseGeoViewerCell, GeoSpatialViewerCell, RasterLayer, \
                            VectorLayer, PolyLayer, PointLayer, LineLayer
from sahm_picklists import ResponseType, AggregationMethod, \
        ResampleMethod, PointAggregationMethod, ModelOutputType, RandomPointType, \
        OutputRaster, mpl_colormap, T_O_M

from utils import writetolog
from pySAHM.utilities import TrappedError
global utilities

identifier = 'gov.usgs.sahm'

doc_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "documentation.xml"))
GenModDoc.load_documentation(doc_file)

def menu_items():
    """ Add a menu item which allows users to specify their session directory
    and select and test the final model
    """
    def change_session_folder():
        global session_dir

        path = str(QtGui.QFileDialog.getExistingDirectory(None,
                                        'Browse to new session folder -', utils.getrootdir()))
        if path == '':
            return None

        if configuration.cur_processing_mode == "FORT Condor" and \
            not utilities.checkIfFolderIsOnNetwork(path):
            return None

        session_dir = path
        utils.setrootdir(path)
        utils.createLogger(session_dir, True)

        configuration.cur_session_folder = path

        package_manager = get_package_manager()
        package = package_manager.get_package(identifier)
        dom, element = package.find_own_dom_element()

        configuration.write_to_dom(dom, element)

        writetolog("*" * 79 + "\n" + "*" * 79)
        writetolog(" output directory:   " + session_dir)
        writetolog("*" * 79 + "\n" + "*" * 79)

    def select_test_final_model():
        global session_dir

        STFM = SelectAndTestFinalModel(session_dir, utils.get_r_path())
        retVal = STFM.exec_()

    def selectProcessingMode():
        selectDialog = QtGui.QDialog()

        global groupBox
        groupBox = QtGui.QGroupBox("Processing mode:")
        vbox = QtGui.QVBoxLayout()

        for mode in [("multiple models simultaneously (1 core each)", True),
                     ("single models sequentially (n - 1 cores each)", True),
                     ("FORT Condor", isFortCondorAvailible())]:
            radio = QtGui.QRadioButton(mode[0])
            radio.setChecked(mode[0] == configuration.cur_processing_mode)
            radio.setEnabled(mode[1])
            QtCore.QObject.connect(radio, QtCore.SIGNAL("toggled(bool)"), selectProcessingMode_changed)
            vbox.addWidget(radio)

        groupBox.setLayout(vbox)

        layout = QtGui.QVBoxLayout()
        layout.addWidget(groupBox)
        selectDialog.setLayout(layout)

        selectDialog.exec_()

    def selectProcessingMode_changed(e):
        if e:
            global groupBox
            qvbl = groupBox.layout()
            for i in range(0, qvbl.count()):
                widget = qvbl.itemAt(i).widget()
                if (widget != 0) and (type(widget) is QtGui.QRadioButton):
                    if widget.isChecked():

                        configuration.cur_processing_mode = str(widget.text())

                        package_manager = get_package_manager()
                        package = package_manager.get_package(identifier)
                        dom, element = package.find_own_dom_element()

                        if configuration.cur_processing_mode == "FORT Condor":
                            if not utilities.checkIfFolderIsOnNetwork(configuration.cur_session_folder):
                                widget = qvbl.itemAt(i - 1).widget()
                                widget.setChecked(True)
                                return

                        configuration.write_to_dom(dom, element)
                        utilities.start_new_pool(utilities.get_process_count(widget.text()))

    def isFortCondorAvailible():
        try:
            cmd = ["condor_store_cred", "-n", "IGSKBACBWSCDRS3", "query"]
            p = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            ret = p.communicate()
            return ret[0].find("A credential is stored and is valid") != -1
        except:
            return False

    lst = []
    lst.append(("Change session folder", change_session_folder))
    lst.append(("Change processing mode", selectProcessingMode))
    lst.append(("Select and test the Final Model", select_test_final_model))
    return(lst)

class FieldData(Path):
    '''
    '''
    __doc__ = GenModDoc.construct_module_doc('FieldData')

#    _input_ports = [('csvFile', '(edu.utah.sci.vistrails.basic:File)')]
    _output_ports = [('value', '(gov.usgs.sahm:FieldData:DataInput)'),
                     ('value_as_string', '(edu.utah.sci.vistrails.basic:String)', True)]

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        out_fname = utils.getFileRelativeToCurrentVT(self.getInputFromPort("value").name, self)
        output_file = utils.create_file_module(out_fname, module=self)
        self.setResult('value', output_file)

class Predictor(Constant):
    '''
    '''
    __doc__ = GenModDoc.construct_module_doc('Predictor')

    _input_ports = [('categorical', '(edu.utah.sci.vistrails.basic:Boolean)'),
                    ('ResampleMethod', '(gov.usgs.sahm:ResampleMethod:Other)', {'defaults':'["Bilinear"]'}),
                    ('AggregationMethod', '(gov.usgs.sahm:AggregationMethod:Other)', {'defaults':'["Mean"]'}),
                    ('file', '(edu.utah.sci.vistrails.basic:Path)')]
    _output_ports = [('value', '(gov.usgs.sahm:Predictor:DataInput)'),
                     ('value_as_string', '(edu.utah.sci.vistrails.basic:String)', True)]

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        if (self.hasInputFromPort("ResampleMethod")):
            resampleMethod = self.getInputFromPort("ResampleMethod")
            if resampleMethod.lower() not in ['nearestneighbor', 'bilinear', 'cubic', 'cubicspline', 'lanczos']:
                raise ModuleError(self,
                                  "Resample Method not one of 'nearestneighbor', 'bilinear', 'cubic', 'cubicspline', or 'lanczos'")
        else:
            resampleMethod = 'Bilinear'

        if (self.hasInputFromPort("AggregationMethod")):
            aggregationMethod = self.getInputFromPort("AggregationMethod")
            if self.getInputFromPort("AggregationMethod").lower() not in ['mean', 'max', 'min', 'std', 'majority', 'none']:
                raise ModuleError(self, "No Aggregation Method specified")
        else:
            aggregationMethod = "Mean"

        if (self.hasInputFromPort("categorical")):
            if self.getInputFromPort("categorical") == True:
                categorical = '1'
            else:
                categorical = '0'
        else:
            categorical = '0'

        if (self.hasInputFromPort("file")):
            out_fname = utils.getFileRelativeToCurrentVT(self.getInputFromPort("file").name, self)
            inFile = utils.getRasterName(out_fname)
        else:
            raise ModuleError(self, "No input file specified")
        self.setResult('value', (inFile, categorical, resampleMethod, aggregationMethod))

class PredictorList(Constant):
    '''
    This module is a required class for other modules and scripts within the
    SAHM package. It is not intended for direct use or incorporation into
    the VisTrails workflow by the user.
    '''
    _input_ports = [('value', '(gov.usgs.sahm:PredictorList:Other)'),
                                 ('addPredictor', '(gov.usgs.sahm:Predictor:DataInput)')]
    _output_ports = [('value', '(gov.usgs.sahm:PredictorList:Other)')]

    @staticmethod
    def translate_to_string(v):
        return str(v)

    @staticmethod
    def translate_to_python(v):
        v_list = eval(v)
        return v_list

    @staticmethod
    def validate(x):
        return type(x) == list

    def compute(self):
        p_list = self.forceGetInputListFromPort("addPredictor")
        v = self.forceGetInputFromPort("value", [])

        b = self.validate(v)
        if not b:
            raise ModuleError(self, "Internal Error: Constant failed validation")
        if len(v) > 0 and type(v[0]) == tuple:
            f_list = [utils.create_file_module(v_elt[0], module=self) for v_elt in v]
        else:
            f_list = v
        p_list += f_list
        #  self.setResult("value", p_list)
        self.setResult("value", v)

class PredictorListFile(Module):
    '''

    '''
    __doc__ = GenModDoc.construct_module_doc('PredictorListFile')

    _input_ports = [('csvFileList', '(edu.utah.sci.vistrails.basic:File)')]
    _output_ports = [('RastersWithPARCInfoCSV', '(gov.usgs.sahm:RastersWithPARCInfoCSV:Other)')]

    #  copies the input predictor list csv to our working directory
    #  and appends any additionally added predictors

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    @staticmethod
    def translate_to_string(v):
        return str(v)

    @staticmethod
    def translate_to_python(v):
        v_list = eval(v)
        return v_list

    @staticmethod
    def validate(x):
        return type(x) == list

    def compute(self):
        if not self.hasInputFromPort("csvFileList"):
            raise ModuleError(self, "No CSV file provided")



        in_csv = utils.getFileRelativeToCurrentVT(self.getInputFromPort("csvFileList").name, self)

        output_file = utils.create_file_module(in_csv, module=self)
        self.setResult('RastersWithPARCInfoCSV', output_file)

class TemplateLayer(Path):
    '''
    '''
    __doc__ = GenModDoc.construct_module_doc('TemplateLayer')

#    _input_ports = [('FilePath', '(edu.utah.sci.vistrails.basic:File)')]
    _output_ports = [('value', '(gov.usgs.sahm:TemplateLayer:DataInput)'),
                     ('value_as_string', '(edu.utah.sci.vistrails.basic:String)', True)]

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        out_fname = utils.getFileRelativeToCurrentVT(self.getInputFromPort("value").name, self)
        output_file = utils.create_file_module(out_fname, module=self)
        self.setResult('value', output_file)

#  class SingleInputPredictor(Predictor):
#    pass
#
#  class SpatialDef(Module):
#    _output_ports = [('spatialDef', '(gov.usgs.sahm:SpatialDef:DataInput)')]

class MergedDataSet(File):
    '''
    This module is a required class for other modules and scripts within the
    SAHM package. It is not intended for direct use or incorporation into
    the VisTrails workflow by the user.
    '''
    _input_ports = [('mdsFile', '(edu.utah.sci.vistrails.basic:File)'), ]
    _output_ports = [('value', '(gov.usgs.sahm:MergedDataSet:Other)'), ]

    pass

class RastersWithPARCInfoCSV(File):
    '''
    This module is a required class for other modules and scripts within the
    SAHM package. It is not intended for direct use or incorporation into
    the VisTrails workflow by the user.
    '''
    _input_ports = [('mdsFile', '(edu.utah.sci.vistrails.basic:File)'), ]
    _output_ports = [('value', '(gov.usgs.sahm:MergedDataSet:Other)'), ]

    pass


class Model(Module):
    '''
    This module is a required class for other modules and scripts within the
    SAHM package. It is not intended for direct use or incorporation into
    the VisTrails workflow by the user.
    '''
    _input_ports = [('ThresholdOptimizationMethod', '(gov.usgs.sahm:T_O_M:Other)', {'defaults':'["Sensitivity=Specificity"]', 'optional':False}),
                    ('mdsFile', '(gov.usgs.sahm:MergedDataSet:Other)'),
                    ('makeBinMap', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["True"]', 'optional':False}),
                    ('makeProbabilityMap', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["True"]', 'optional':False}),
                    ('makeMESMap', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["False"]', 'optional':False}),
                    ('outputFolderName', '(edu.utah.sci.vistrails.basic:String)'),
                    ('run_name_info', '(gov.usgs.sahm:OutputNameInfo:Other)', {'optional':True}), ]

    _output_ports = [('modelWorkspace', '(edu.utah.sci.vistrails.basic:Directory)'),
                     ('BinaryMap', '(edu.utah.sci.vistrails.basic:File)'),
                     ('ProbabilityMap', '(edu.utah.sci.vistrails.basic:File)'),
                     ('ResidualsMap', '(edu.utah.sci.vistrails.basic:File)'),
                     ('MessMap', '(edu.utah.sci.vistrails.basic:File)'),
                     ('MoDMap', '(edu.utah.sci.vistrails.basic:File)'),
                     ('modelEvalPlot', '(edu.utah.sci.vistrails.basic:File)'),
                     ('Text_Output', '(edu.utah.sci.vistrails.basic:File)'),
                     ('ModelVariableImportance', '(edu.utah.sci.vistrails.basic:File)')]

    port_map = {'mdsFile':('c', None, True),  #  These ports are for all Models
                         'makeProbabilityMap':('mpt', utils.R_boolean, True),
                         'makeBinMap':('mbt', utils.R_boolean, True),
                         'makeMESMap':('mes', utils.R_boolean, True),
                         'ThresholdOptimizationMethod':('om', None, False),
                    }


    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def __init__(self):
        self.suspended_completed = False
        self.pywrapper = "runRModel.py"
        self.port_map = copy.deepcopy(Model.port_map)
        self.output_dname = None
        Module.__init__(self)

    def compute(self):
        out_folder = self.forceGetInputFromPort("outputFolderName", "")


        self.args_dict = utils.map_ports(self, self.port_map)

        mdsFile = utils.getFileRelativeToCurrentVT(self.args_dict['c'], self)

        if self.hasInputFromPort('run_name_info'):
            runinfo = self.forceGetInputFromPort('run_name_info')
            subfolder = runinfo.contents.get('subfolder', "")
            runname = runinfo.contents.get('runname', "")
        else:
            subfolder, runname = utils.get_previous_run_info(mdsFile)

        if runname and out_folder:
            prefix = "_".join([self.abbrev, runname, out_folder])
        elif runname:
            prefix = "_".join([self.abbrev, runname])
        elif out_folder:
            prefix = "_".join([self.abbrev, out_folder])
        else:
            prefix = self.abbrev

        #  convert threshold optimization string to the expected integer
        thresholds = {"Threshold=0.5":1,
                      "Sensitivity=Specificity":2,
                      "Maximizes (sensitivity+specificity)/2":3,
                      "Maximizes Cohen's Kappa":4,
                      "Maximizes PCC (percent correctly classified)":5,
                      "Predicted prevalence=observed prevalence":6,
                      "Threshold=observed prevalence":7,
                      "Mean predicted probability":8,
                      "Minimizes distance between ROC plot and (0,1)":9}
        self.args_dict["om"] = thresholds.get(self.args_dict.get("om", "Sensitivity=Specificity"))

        if not utils.checkModelCovariatenames(mdsFile):
            msg = "These R models do not work with covariate names begining with non-letter characters or \n"
            msg += "covariate names that contain non-alphanumeric characters other than '.' or '_'.\n"
            msg += "Please check your covariate names and rename any that do not meet these constraints.\n"
            msg += "Covaraiate names are found in the first line of the mds file: \n"
            msg += "\t\t" + mdsFile
            writetolog(msg, False, True)
            raise ModuleError(self, msg)

        if self.abbrev == "Maxent":
            global maxent_path
            self.args_dict['maxent_path'] = maxent_path
            global java_path
            self.args_dict['java_path'] = java_path
            self.args_dict['maxent_args'] = self.maxent_args

        self.args_dict['rc'] = utils.MDSresponseCol(mdsFile)
        self.args_dict['cur_processing_mode'] = configuration.cur_processing_mode


        self.output_dname, signature, already_run = utils.make_next_file_complex(self, prefix, key_inputs=[mdsFile],
                                                                                file_or_dir='dir', subfolder=subfolder)
        copy_mds_fname = os.path.join(self.output_dname, os.path.split(mdsFile)[1])
        if not os.path.exists(copy_mds_fname):
            shutil.copyfile(mdsFile, copy_mds_fname)
        self.args_dict["c"] = copy_mds_fname

#            self.output_dname = utils.find_model_dir(prefix, self.args_dict)

        if self.abbrev == 'brt' or \
            self.abbrev == 'rf':
            if not "seed" in self.args_dict.keys():
                self.args_dict['seed'] = utils.get_seed()
            writetolog("    seed used for " + self.abbrev + " = " + str(self.args_dict['seed']))

        self.args_dict['o'] = self.output_dname

        #  This give previously launched models time to finish writing their
        #  logs so we don't get a lock
        time.sleep(2)

        utils.write_hash_entry_pickle(signature, self.output_dname)

        try:
            utils.run_model_script(self.name, self.args_dict, self, self.pywrapper)
        except ModuleSuspended:
            raise
        except:
            utils.delete_hash_entry_pickle(signature)
            raise

        self.set_model_results()

    def set_model_results(self,):
        #  set our output ports
        #  if an output is expected and we're running in syncronously then throw
        #  an error
        if not self.args_dict.has_key('mes'):
            self.args_dict['mes'] = 'FALSE'
        self.outputRequired = configuration.cur_processing_mode == "single models sequentially (n - 1 cores each)"
        self.setModelResult("_prob_map.tif", 'ProbabilityMap', self.abbrev)
        self.setModelResult("_bin_map.tif", 'BinaryMap', self.abbrev)
        self.setModelResult("_resid_map.tif", 'ResidualsMap', self.abbrev)
        self.setModelResult("_mess_map.tif", 'MessMap', self.abbrev)
        self.setModelResult("_MoD_map.tif", 'MoDMap', self.abbrev)
        self.setModelResult("_output.txt", 'Text_Output', self.abbrev)
        self.setModelResult("_modelEvalPlot.png", 'modelEvalPlot', self.abbrev)
        self.setModelResult("_variable.importance.png", 'ModelVariableImportance', self.abbrev)
        writetolog("Finished " + self.abbrev + " builder\n", True, True)

        modelWorkspace = utils.create_dir_module(self.output_dname)
        self.setResult("modelWorkspace", modelWorkspace)

    def setModelResult(self, filename, portname, abbrev):
        '''sets a single output port value
        '''
        outFileName = os.path.join(self.output_dname, abbrev + filename)
        output_file = File()
        output_file.name = outFileName
        output_file.upToDate = True

        self.setResult(portname, output_file)

class GLM(Model):
    __doc__ = GenModDoc.construct_module_doc('GLM')

    _input_ports = list(Model._input_ports)
    _input_ports.extend([('SelectBestPredSubset', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["True"]', 'optional':True}),
                         ('SimplificationMethod', '(edu.utah.sci.vistrails.basic:String)', {'defaults':'["AIC"]', 'optional':True}),
                         ('SquaredTerms', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["True"]', 'optional':True}),
                         ])
    def __init__(self):
        global models_path
        Model.__init__(self)
        self.name = 'FIT_GLM_pluggable.r'
        self.abbrev = 'glm'
        self.port_map.update({'SimplificationMethod':('sm', None, False),  #  This is a GLM specific port
                         'SquaredTerms':('sqt', utils.R_boolean, False),  #  This is a GLM specific port
                         'SelectBestPredSubset':('pst', utils.R_boolean, False),  #  This is a GLM specific port
                         })

class RandomForest(Model):
    __doc__ = GenModDoc.construct_module_doc('RandomForest')

    _input_ports = list(Model._input_ports)
    _input_ports.extend([('Seed', '(edu.utah.sci.vistrails.basic:Integer)', {'defaults':'["{}"]'.format(utils.get_seed()), 'optional':True}),
                         ('mTry', '(edu.utah.sci.vistrails.basic:Integer)', {'defaults':'["1"]', 'optional':True}),
                         ('nTrees', '(edu.utah.sci.vistrails.basic:Integer)', {'optional':True}),
                         ('nodesize', '(edu.utah.sci.vistrails.basic:Integer)', {'optional':True}),
                         ('replace', '(edu.utah.sci.vistrails.basic:Boolean)', {'optional':True}),
                         ('maxnodes', '(edu.utah.sci.vistrails.basic:Integer)', {'optional':True}),
                         ('importance', '(edu.utah.sci.vistrails.basic:Boolean)', {'optional':True}),
                         ('localImp', '(edu.utah.sci.vistrails.basic:Boolean)', {'optional':True}),
                         ('proximity', '(edu.utah.sci.vistrails.basic:Boolean)', {'optional':True}),
                         ('oobProx', '(edu.utah.sci.vistrails.basic:Boolean)', {'optional':True}),
                         ('normVotes', '(edu.utah.sci.vistrails.basic:Boolean)', {'optional':True}),
                         ])
    def __init__(self):
        global models_path
        Model.__init__(self)
        self.name = 'FIT_RF_pluggable.r'
        self.abbrev = 'rf'
        self.port_map.update({'Seed':('seed', utils.get_seed, True),  #  This is a BRT specific port
                         'mTry': ('mtry', None, False),  #  This is a Random Forest specific port
                         'nodesize': ('nodeS', None, False),  #  This is a Random Forest specific port
                         'replace': ('sampR', utils.R_boolean, False),  #  This is a Random Forest specific port
                         'maxnodes': ('maxN', None, False),  #  This is a Random Forest specific port
                         'importance': ('impt', utils.R_boolean, False),  #  This is a Random Forest specific port
                         'localImp': ('locImp', utils.R_boolean, False),  #  This is a Random Forest specific port
                         'proximity': ('prox', utils.R_boolean, False),  #  This is a Random Forest specific port
                         'oobPorx': ('oopp', utils.R_boolean, False),  #  This is a Random Forest specific port
                         'normVotes': ('nVot', utils.R_boolean, False),  #  This is a Random Forest specific port
                         'doTrace': ('Trce', utils.R_boolean, False),  #  This is a Random Forest specific port
                         'keepForest': ('kf', utils.R_boolean, False),  #  This is a Random Forest specific port
                         })

class MARS(Model):
    __doc__ = GenModDoc.construct_module_doc('MARS')

    _input_ports = list(Model._input_ports)
    _input_ports.extend([('MarsDegree', '(edu.utah.sci.vistrails.basic:Integer)', {'defaults':'["1"]', 'optional':True}),
                         ('MarsPenalty', '(edu.utah.sci.vistrails.basic:Float)', {'defaults':'["2.0"]', 'optional':True}),
                          ])
    def __init__(self):
        global models_path
        Model.__init__(self)
        self.name = 'FIT_MARS_pluggable.r'
        self.abbrev = 'mars'
        self.port_map.update({'MarsDegree':('deg', None, False),  #  This is a MARS specific port
                         'MarsPenalty':('pen', None, False),  #  This is a MARS specific port
                         })

class ApplyModel(Model):
    __doc__ = GenModDoc.construct_module_doc('ApplyModel')
    _input_ports = list(Model._input_ports)
    _input_ports.insert(0, ('modelWorkspace', '(edu.utah.sci.vistrails.basic:Directory)'))
#    _input_ports.insert(1, ('evaluateHoldout', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["False"]', 'optional':False}))
#    _input_ports.extend([('modelWorkspace', '(edu.utah.sci.vistrails.basic:Directory)')])

    def __init__(self):
        global models_path
        Model.__init__(self)
        self.name = 'EvaluateNewData.r'
        self.abbrev = 'ApplyModel'
        self.port_map.update({'modelWorkspace':('ws',
                lambda x: os.path.join(utils.dir_path_value(x), "modelWorkspace"), True), })

    def compute(self):
        #  if the suplied mds has rows, observations then
        #  pass r code the flag to produce metrics
        mdsfname = utils.getFileRelativeToCurrentVT(self.forceGetInputFromPort('mdsFile').name, self)
        mdsfile = open(mdsfname, "r")
        lines = 0
        readline = mdsfile.readline
        while readline():
            lines += 1
            if lines > 4:
                break

        if lines > 3:
            #  we have rows R will need to recreate metrics.
            self.args = 'pmt=TRUE '
        else:
            self.args = 'pmt=FALSE '

        Model.compute(self)

class BoostedRegressionTree(Model):
    __doc__ = GenModDoc.construct_module_doc('BoostedRegressionTree')

    _input_ports = list(Model._input_ports)
    _input_ports.extend([('Seed', '(edu.utah.sci.vistrails.basic:Integer)', {'defaults':'["{}"]'.format(utils.get_seed()), 'optional':True}),
                              ('TreeComplexity', '(edu.utah.sci.vistrails.basic:Integer)', {'optional':True}),
                              ('BagFraction', '(edu.utah.sci.vistrails.basic:Float)', {'defaults':'["0.75"]', 'optional':True}),
                              ('NumberOfFolds', '(edu.utah.sci.vistrails.basic:Integer)', {'defaults':'["3"]', 'optional':True}),
                              ('Alpha', '(edu.utah.sci.vistrails.basic:Float)', {'defaults':'["1"]', 'optional':True}),
                              ('PrevalenceStratify', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["True"]', 'optional':True}),
                              ('ToleranceMethod', '(edu.utah.sci.vistrails.basic:String)', {'defaults':'["auto"]', 'optional':True}),
                              ('Tolerance', '(edu.utah.sci.vistrails.basic:Float)', {'defaults':'["0.001"]', 'optional':True}),
                              ('LearningRate', '(edu.utah.sci.vistrails.basic:Float)', {'optional':True}),
                              ('SelectBestPredSubset', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["True"]', 'optional':True}),
                              ('NumberOfTrees', '(edu.utah.sci.vistrails.basic:Integer)', {'optional':True}),
                              ])
    def __init__(self):
        global models_path
        Model.__init__(self)
        self.name = 'FIT_BRT_pluggable.r'
        self.abbrev = 'brt'
        self.port_map.update({'Seed':('seed', None, False),  #  This is a BRT specific port
                         'TreeComplexity':('tc', None, False),  #  This is a BRT specific port
                         'BagFraction':('bf', None, False),  #  This is a BRT specific port
                         'NumberOfFolds':('nf', None, False),  #  This is a BRT specific port
                         'Alpha':('alp', None, False),  #  This is a BRT specific port
                         'PrevalenceStratify':('ps', None, False),  #  This is a BRT specific port
                         'ToleranceMethod':('tolm', None, False),  #  This is a BRT specific port
                         'Tolerance':('tol', None, False),  #  This is a BRT specific port
                         'LearningRate':('lr', None, False),  #  This is a BRT specific port
                         'NumberOfTrees':('ntr', None, False),  #  This is a BRT specific port
                         'SelectBestPredSubset':('pst', utils.R_boolean, False),  #  This is a BRT specific port
                         })

class MAXENT(Model):
    '''

    '''
    _input_ports = list(Model._input_ports)
    _input_ports.extend([('UseRMetrics', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["True"]', 'optional':True}),
                         ])
    _output_ports = list(Model._output_ports)
    _output_ports.extend([("lambdas", "(edu.utah.sci.vistrails.basic:File)"),
                     ("report", "(edu.utah.sci.vistrails.basic:File)"),
                     ("roc", "(edu.utah.sci.vistrails.basic:File)")])

    def __init__(self):
        global models_path
        Model.__init__(self)
        self.name = 'WrapMaxent.r'
        self.pywrapper = "runMaxent.py"
        self.abbrev = 'Maxent'
        self.port_map.update({'species_name':('species_name', None, True),  #  This is a Maxent specific port
                              })

    def compute(self):

        self.maxent_args = {}
        for port in self._input_ports:

            if not port in list(Model._input_ports) and \
                port[0] <> 'projectionlayers' and \
                port[0] <> 'UseRMetrics' and \
                port[0] <> 'species_name':
                if self.hasInputFromPort(port[0]):
                    port_val = self.getInputFromPort(port[0])
                    if port[1] == "(edu.utah.sci.vistrails.basic:Boolean)":
                        port_val = str(port_val).lower()
                    elif (port[1] == "(edu.utah.sci.vistrails.basic:Path)" or \
                        port[1] == "(edu.utah.sci.vistrails.basic:File)" or \
                        port[1] == "(edu.utah.sci.vistrails.basic:Directory)"):
                        port_val = port_val.name
                    self.maxent_args[port[0]] = port_val
                else:
                    kwargs = port[2]
                    try:
                        if port[1] == "(edu.utah.sci.vistrails.basic:Boolean)":
                            default = kwargs['defaults'][1:-1].lower()
                        elif port[1] == "(edu.utah.sci.vistrails.basic:String)":
                            default = kwargs['defaults'][1:-1]
                        else:
                            default = kwargs['defaults'][1:-1]
                        #  args[port[0]] = default
                        self.maxent_args[port[0]] = default[1:-1]
                    except KeyError:
                        pass
        if self.hasInputFromPort('projectionlayers'):
            value = self.forceGetInputListFromPort('projectionlayers')
            projlayers = ','.join([path.name for path in value])
            self.maxent_args['projectionlayers'] = projlayers

        Model.compute(self)

#       set some Maxent specific outputs
        self.args_dict['species_name'] = self.args_dict['species_name'].replace(' ', '_')
        lambdasfile = self.args_dict["species_name"] + ".lambdas"
        self.setModelResult(lambdasfile, "lambdas", "")

        rocfile = "plots" + os.sep + self.args_dict["species_name"] + "_roc.png"
        self.setModelResult(rocfile, "roc", "")

        htmlfile = self.args_dict["species_name"] + ".html"
        self.setModelResult(htmlfile, "report", "")

        writetolog("Finished Maxent", True)

class HabitatSuitabilityCurve(Model):
    '''
    '''
    _input_ports = list(Model._input_ports)
    _input_ports.extend([('UseRMetrics', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["True"]', 'optional':True}),
                         ])
    _output_ports = list(Model._output_ports)
    _output_ports.extend([("curves_json", "(edu.utah.sci.vistrails.basic:File)")])

    def __init__(self):
        global models_path
        Model.__init__(self)
        self.name = 'FIT_HSC.r'
        self.pywrapper = "runRModel.py"
        self.abbrev = 'hsc'

    def compute(self):

        Model.compute(self)

        self.setModelResult("hsc.json", "curves_json", "")

        writetolog("Finished HSC", True)


class BackgroundSurfaceGenerator(Module):
    '''
    '''
    __doc__ = GenModDoc.construct_module_doc('BackgroundSurfaceGenerator')

    _input_ports = [('templateLayer', '(gov.usgs.sahm:TemplateLayer:DataInput)'),
                    ('fieldData', '(gov.usgs.sahm:FieldData:DataInput)'),
                        ('method', '(edu.utah.sci.vistrails.basic:String)', {'defaults':'["KDE"]', 'optional':True}),
                        ('bandwidthOptimizationMethod', '(edu.utah.sci.vistrails.basic:String)', {'defaults':'["adhoc"]', 'optional':True}),
                        ('isopleth', '(edu.utah.sci.vistrails.basic:Integer)', {'defaults':'["95"]', 'optional':True}),
                        ('continuous', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["False"]', 'optional':True}),
                        ('run_name_info', '(gov.usgs.sahm:OutputNameInfo:Other)')]
    _output_ports = [("KDE", "(edu.utah.sci.vistrails.basic:File)")]

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        port_map = {'templateLayer': ('templatefName', None, True),
                    'fieldData': ('fieldData', None, False),
            'method': ('method', None, True),
            'bandwidthOptimizationMethod': ('bandOptMeth', None, True),
            'isopleth': ('isopleth', None, True),
            'continuous': ('continuous', utils.R_boolean, True),
            'run_name_info': ('run_name_info', None, False), }

        kde_params = utils.map_ports(self, port_map)

        run_name_info = kde_params.get('run_name_info')
        if run_name_info:
            subfolder = run_name_info.contents.get('subfolder_name', "")
            runname = run_name_info.contents.get('runname', "")
        else:
            subfolder, runname = utils.get_previous_run_info(kde_params['fieldData'])

        global models_path
        prefix = os.path.splitext(os.path.split(kde_params["fieldData"])[1])[0]
        suffix = kde_params["method"]
        if kde_params["method"] == "KDE":
            suffix += kde_params["bandOptMeth"]
            if kde_params["continuous"] == "TRUE":
                suffix += "_continuous"
            else:
                suffix += "_iso" + str(kde_params["isopleth"])
        suffix += ".tif"

        output_fname, signature, already_run = utils.make_next_file_complex(self,
                                        prefix=prefix, suffix=suffix,
                                        key_inputs=[kde_params['fieldData'], utils.get_raster_files(kde_params['templatefName'])],
                                        subfolder=subfolder, runname=runname)

        if already_run:
            writetolog("No change in inputs or paramaters using previous run of BackgroundSurfaceGenerator", True)
        else:
            args = {"tmplt":kde_params["templatefName"],
                    "i":kde_params["fieldData"],
                    "o":output_fname,
                    "mth":kde_params["method"],
                    "bwopt":kde_params["bandOptMeth"],
                    "ispt":str(kde_params["isopleth"]),
                    "continuous":kde_params["continuous"]}

            utils.run_R_script("PseudoAbs.r", args, self, new_r_path=configuration.r_path)

        if os.path.exists(output_fname):
            output_file = utils.create_file_module(output_fname, module=self)
            writetolog("Finished KDE generation ", True)
        else:
            msg = "Problem encountered generating KDE.  Expected output file not found."
            writetolog(msg, False)
            raise ModuleError(self, msg)

        utils.write_hash_entry_pickle(signature, output_fname)
        self.setResult("KDE", output_file)

class OutputNameInfo(Constant):
    contents = {}

    @staticmethod
    def translate_to_python(x):
        try:
            runinfo = OutputNameInfo()
            runinfo.contents = {'runname':str(x),
                                'subfolder_name':'',
                                'delete_previous':False}
            return runinfo
        except:
            return None

class OutputName(Module):
    __doc__ = GenModDoc.construct_module_doc('OutputName')

    _input_ports = [('run_name', '(edu.utah.sci.vistrails.basic:String)', {'defaults':'[""]', 'optional':True}),
                                 ('subfolder_name', '(edu.utah.sci.vistrails.basic:String)', {'defaults':'[""]', 'optional':True}),
                                 ('delete_previous', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["False"]', 'optional':True}), ]


    _output_ports = [('run_name_info', '(gov.usgs.sahm:OutputNameInfo:Other)')]

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        port_map = {'run_name': ('runname', None, True),
                    'subfolder_name': ('subfolder_name', None, True),
                    'delete_previous': ('delete_previous', None, True), }

        name_info = utils.map_ports(self, port_map)

        if not name_info.has_key('runname') and not name_info.has_key('subfolder_name'):
            raise ModuleError(self, "either 'run_name' or 'subfolder_name' must be supplied")

        if name_info['runname'] and not name_info['runname'].isalnum():
            raise ModuleError(self, "run_name cannot contain spaces or any characters other than letters and numbers")

        if name_info['delete_previous']:
            #  do our best to clear out any previous contents with this name
            if name_info['subfolder_name'] != "":
                subfolder = os.path.join(utils.getrootdir(), name_info['subfolder_name'])
                shutil.rmtree(subfolder, ignore_errors=True)

            if name_info['runname'] != "":
                for fname in os.listdir(utils.getrootdir()):
                    if "_" + name_info['runname'] + "_" in fname:
                        fname = os.path.join(utils.getrootdir(), name_info['runname'])
                        os.unlink(fname)
        subfolder = os.path.join(utils.getrootdir(), name_info['subfolder_name'])
        if name_info['subfolder_name'] != "" and not os.path.exists(subfolder):
            os.makedirs(subfolder)

        runinfo = OutputNameInfo()
        runinfo.contents = name_info
        self.setResult('run_name_info', runinfo)


class MDSBuilder(Module):
    '''
    '''
    __doc__ = GenModDoc.construct_module_doc('MDSBuilder')

    _input_ports = [('RastersWithPARCInfoCSV', '(gov.usgs.sahm:RastersWithPARCInfoCSV:Other)'),
                                 ('fieldData', '(gov.usgs.sahm:FieldData:DataInput)'),
#                                 ('backgroundPointType', '(gov.usgs.sahm:RandomPointType:Other)', {'defaults':'["Background"]'}),
                                 ('backgroundPointCount', '(edu.utah.sci.vistrails.basic:Integer)'),
                                 ('backgroundProbSurf', '(edu.utah.sci.vistrails.basic:File)'),
                                 ('Seed', '(edu.utah.sci.vistrails.basic:Integer)', {'defaults':'["{}"]'.format(utils.get_seed()), 'optional':True}),
                                 ('run_name_info', '(gov.usgs.sahm:OutputNameInfo:Other)')]


    _output_ports = [('mdsFile', '(gov.usgs.sahm:MergedDataSet:Other)')]

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        port_map = {'fieldData': ('fieldData', None, False),
#                    'backgroundPointType': ('pointType', None, False),
                    'backgroundPointCount': ('pointCount', None, False),
                    'backgroundProbSurf': ('probSurfacefName', None, False),
                    'Seed': ('seed', utils.get_seed, True),
                    'run_name_info': ('run_name_info', None, False), }

        MDSParams = utils.map_ports(self, port_map)

        run_name_info = MDSParams.get('run_name_info')
        if run_name_info:
            subfolder = run_name_info.contents.get('subfolder_name', "")
            runname = run_name_info.contents.get('runname', "")
        else:
            subfolder, runname = utils.get_previous_run_info(
                                                MDSParams.get('fieldData', ''))

        inputs_csvs = self.forceGetInputListFromPort('RastersWithPARCInfoCSV')
        if len(inputs_csvs) == 0:
            raise ModuleError(self, "Must supply at least one 'RastersWithPARCInfoCSV'/nThis is the output from the PARC module")


            #  inputsCSV = utils.path_port(self, 'RastersWithPARCInfoCSV')
        key_inputs = []
        for input in ['fieldData']:
            if MDSParams.has_key(input):
                key_inputs.append(MDSParams[input])

        inputs_names = [utils.getFileRelativeToCurrentVT(f.name, self) for f in inputs_csvs]
        for fname in inputs_names:
            key_inputs.append(fname)

        if MDSParams.has_key('probSurfacefName'):
            key_inputs.append(MDSParams['probSurfacefName'])
        key_inputs.append(MDSParams['seed'])

        MDSParams['outputMDS'], signature, already_run = utils.make_next_file_complex(self,
                                        prefix='MergedDataset', suffix='.csv',
                                        key_inputs=key_inputs,
                                        subfolder=subfolder, runname=runname)

        if already_run:
            writetolog("No change in inputs or paramaters using previous run of MDS Builder", True)
        else:
            inputs_csv = utils.mknextfile(prefix='CombinedPARCFiles', suffix='.csv', subfolder=subfolder, runname=runname)
            inputs_names = [utils.getFileRelativeToCurrentVT(f.name, self) for f in inputs_csvs]
            utils.merge_inputs_csvs(inputs_names, inputs_csv)
            MDSParams['inputsCSV'] = inputs_csv

            ourMDSBuilder = MDSB.MDSBuilder()
            utils.PySAHM_instance_params(ourMDSBuilder, MDSParams)

            writetolog("    inputsCSV=" + ourMDSBuilder.inputsCSV, False, False)
            writetolog("    fieldData=" + ourMDSBuilder.fieldData, False, False)
            writetolog("    outputMDS=" + ourMDSBuilder.outputMDS, False, False)

            try:
                ourMDSBuilder.run()
            except TrappedError as e:
                raise ModuleError(self, e.message)
            except:
                utils.informative_untrapped_error(self, "MDSBuilder")

        output_file = utils.create_file_module(MDSParams['outputMDS'], module=self)
        utils.write_hash_entry_pickle(signature, MDSParams['outputMDS'])
        self.setResult('mdsFile', output_file)

class FieldDataQuery(Module):
    '''
    A wrapper to instantiate and run the FieldDataQuery module from PySAHM
    '''
    __doc__ = GenModDoc.construct_module_doc('FieldDataQuery')

    _input_ports = [('fieldData_file', '(gov.usgs.sahm:FieldData:DataInput)'),
                                 ('x_column', '(edu.utah.sci.vistrails.basic:String)', {'defaults':'["1"]'}),
                                 ('y_column', '(edu.utah.sci.vistrails.basic:String)', {'defaults':'["2"]'}),
                                 ('Response_column', '(edu.utah.sci.vistrails.basic:String)', {'defaults':'["3"]'}),
                                 ('Response_Presence_value', '(edu.utah.sci.vistrails.basic:String)', {'defaults':'["1"]'}),
                                 ('Response_Absence_value', '(edu.utah.sci.vistrails.basic:String)', {'defaults':'["0"]'}),
                                 ('ResponseType', '(gov.usgs.sahm:ResponseType:Other)', {'defaults':'["Presence(Absence)"]'}),
                                  ('Query_column', '(edu.utah.sci.vistrails.basic:String)'),
                                  ('Query', '(edu.utah.sci.vistrails.basic:String)'),
                                  ('run_name_info', '(gov.usgs.sahm:OutputNameInfo:Other)')]
    _output_ports = [('fieldData', '(gov.usgs.sahm:FieldData:DataInput)'), ]

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        writetolog("\nRunning FieldDataQuery", True)
        port_map = {'fieldData_file': ('fieldData', None, True),
            'x_column': ('x_col', None, True),
            'y_column': ('y_col', None, True),
            'Response_column': ('res_col', None, True),
            'Response_Presence_value': ('res_pres_val', None, True),
            'Response_Absence_value': ('res_abs_val', None, True),
            'ResponseType': ('response_type', None, True),
            'Query_column': ('query_col', None, False),
            'Query': ('query', None, False),
            'run_name_info': ('run_name_info', None, False), }

        FDQParams = utils.map_ports(self, port_map)
#          FDQOutput = utils.mknextfile(prefix='FDQ_', suffix='.csv')

        infile = open(FDQParams['fieldData'], "rb")
        csvReader = csv.DictReader(infile)

        run_name_info = FDQParams.get('run_name_info')
        if run_name_info:
            subfolder = run_name_info.contents.get('subfolder_name', "")
            runname = run_name_info.contents.get('runname', "")
        else:
            subfolder, runname = "", ""

        FDQOutput, signature, already_run = utils.make_next_file_complex(self,
                                        prefix='FDQ', suffix='.csv',
                                        key_inputs=[FDQParams['fieldData']],
                                        subfolder=subfolder, runname=runname)

        if already_run:
            writetolog("No change in inputs or paramaters using previous run of FieldDataQuery", True)
        else:
            outfile = open(FDQOutput, "wb")
            csvwriter = csv.writer(outfile)
            if FDQParams["response_type"] == 'Count':
                responsetype = 'responseCount'
            else:
                responsetype = 'responseBinary'

            csvwriter.writerow(['X', 'Y', responsetype, "input=" + infile.name])

            header = csvReader.fieldnames
            x_key = self.find_column(header, FDQParams['x_col'])
            y_key = self.find_column(header, FDQParams['y_col'])
            res_key = self.find_column(header, FDQParams['res_col'])

            use_query = False
            if self.hasInputFromPort('Query'):
                use_query = True
                query = FDQParams['query']
                #  check if we're using a simple (equality) or complex (python syntax) query
                use_complex = any(s in query for s in ['[' + s + ']' for s in header])

            if self.hasInputFromPort('Query_column'):
                query_col_key = self.find_column(header, FDQParams['query_col'])
            else:
                query_col_key = None

            for row in csvReader:
                if not use_query:
                    include_row = True
                elif use_complex:
                    include_row = self.complex_query(row, query)
                else:
                    include_row = self.simple_query(row, query, query_col_key)

                if include_row:
                    response = row[res_key]
                    if response.lower() in ["1", "true", "t", "present", "presence", str(FDQParams['res_pres_val']).lower()]:
                        response = 1
                    elif response.lower() in ["0", "false", "f", "absent", "absense", str(FDQParams['res_abs_val']).lower()]:
                        response = 0
                    elif responsetype == 'responseBinary':
                        try:
                            response = int(response)
                            if response > 0:
                                response = 1
                        except ValueError:
                            response = row[res_key]
                    else:
                        response = row[res_key]

                    csvwriter.writerow([row[x_key],
                                        row[y_key],
                                        response])

            del infile
            del outfile

        output_file = utils.create_file_module(FDQOutput, module=self)
        utils.write_hash_entry_pickle(signature, FDQOutput)
        self.setResult('fieldData', output_file)


    def find_column(self, header, column):
        try:
            index = int(column) - 1
            if index > len(header) - 1:
                msg = "Field data input contains fewer columns than the number specified\n"
                msg += str(index + 1) + " is greater than " + str(len(header))
                writetolog(msg, True, True)
                raise ModuleError(self, msg)
            return header[index]
        except ValueError:
            if column in header:
                return column
            else:
                msg = "The specified column wasn't in the input file\n"
                msg += column + " not in " + str(header)
                writetolog(msg, True, True)
                raise ModuleError(self, msg)

    def simple_query(self, row, query, query_col):
        return row[query_col] == query

    def complex_query(self, row, query):

        for key in row.keys():
            query = query.replace('[' + key + ']', row[key])
        try:
            return eval(query)
        except NameError:
            msg = "There was a 'NameError' in the complex query you entered.\n"
            msg += "This is often an indication that strings are not being properly quoted in the python syntax.\n"
            msg += "Try enclosing the [fieldName] item in quotes.\n\n"
            msg += 'For example:  "[SourceType]" == "Expert"  instead of  [SourceType] == "Expert"'
            writetolog(msg, True, True)
            raise ModuleError(self, msg)

class FieldDataAggregateAndWeight(Module):
    '''
    Sanity!
    '''
    _input_ports = [('templateLayer', '(gov.usgs.sahm:TemplateLayer:DataInput)'),
                                 ('fieldData', '(gov.usgs.sahm:FieldData:DataInput)'),
                                 ('PointAggregationOrWeightMethod', '(gov.usgs.sahm:PointAggregationMethod:Other)', {'defaults':'["Collapse In Pixel"]'}),
                                 ('FD_EPSG_projection', '(edu.utah.sci.vistrails.basic:Integer)'),
                                  ('run_name_info', '(gov.usgs.sahm:OutputNameInfo:Other)'),
                                  ('drop_nodata_points', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["True"]', 'optional':False}), ]
    _output_ports = [('fieldData', '(gov.usgs.sahm:FieldData:DataInput)')]

    __doc__ = GenModDoc.construct_module_doc('FieldDataAggregateAndWeight')

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        writetolog("\nFieldDataAggregateAndWeight", True)
        port_map = {'templateLayer': ('templatefName', None, True),
            'fieldData': ('csv', None, True),
            'PointAggregationOrWeightMethod': ('aggMethod', None, True),
            'SDofGaussianKernel': ('sd', None, False),
            'FD_EPSG_projection': ('epsg', None, False),
            'run_name_info': ('run_name_info', None, False),
            'drop_nodata_points':('drop_nodata_points', None, True), }

        FDAWParams = utils.map_ports(self, port_map)
#          output_fname = utils.mknextfile(prefix='FDAW_', suffix='.csv')

        run_name_info = FDAWParams.get('run_name_info')
        if run_name_info:
            subfolder = run_name_info.contents.get('subfolder_name', "")
            runname = run_name_info.contents.get('runname', "")
        else:
            subfolder, runname = utils.get_previous_run_info(FDAWParams['csv'])

        template_fname = FDAWParams['templatefName']
        if os.path.isdir(template_fname):
            template_fname = os.path.join(template_fname, "hdr.adf")
        output_fname, signature, already_run = utils.make_next_file_complex(self,
                                        prefix='FDAW', suffix='.csv',
                                        key_inputs=[FDAWParams['csv'], utils.get_raster_files(template_fname)],
                                        subfolder=subfolder, runname=runname)

        if already_run:
            writetolog("No change in inputs or paramaters using previous run of FieldDataAggregateAndWeight", True)
        else:
            writetolog("    output_fname=" + output_fname, True, False)
            FDAWParams['output'] = output_fname

            ourFDAW = FDAW.FieldDataQuery()
            utils.PySAHM_instance_params(ourFDAW, FDAWParams)
            ourFDAW.processCSV()

        output_file = utils.create_file_module(output_fname, module=self)
        writetolog("Finished running FieldDataAggregateAndWeight", True)
        utils.write_hash_entry_pickle(signature, output_fname)
        self.setResult('fieldData', output_file)

class PARC(Module):
    '''
    '''
    __doc__ = GenModDoc.construct_module_doc('PARC')

    _input_ports = [('predictor', "(gov.usgs.sahm:Predictor:DataInput)"),
                                ('PredictorList', '(gov.usgs.sahm:PredictorList:Other)'),
                                ('RastersWithPARCInfoCSV', '(gov.usgs.sahm:RastersWithPARCInfoCSV:Other)'),
                                ('templateLayer', '(gov.usgs.sahm:TemplateLayer:DataInput)'),
                                ('ignoreNonOverlap', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["False"]', 'optional':True}),
                                ('run_name_info', '(gov.usgs.sahm:OutputNameInfo:Other)')]

    _output_ports = [('RastersWithPARCInfoCSV', '(gov.usgs.sahm:RastersWithPARCInfoCSV:Other)')]

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        #  writetolog("\nRunning PARC", True)

        ourPARC = parc.PARC()
        template = utils.getFileRelativeToCurrentVT(self.forceGetInputFromPort('templateLayer').name, self)
        template_path, template_fname = os.path.split(template)
        template_fname = SpatialUtilities.getRasterShortName(template)

        run_name_info = self.forceGetInputFromPort('run_name_info', None)
        if run_name_info:
            subfolder = run_name_info.contents.get('subfolder_name', "")
            runname = run_name_info.contents.get('runname', "")
            if runname:
                output_dname = os.path.join(utils.getrootdir(), subfolder, 'PARC_' + runname + "_" + template_fname)
            else:
                output_dname = os.path.join(utils.getrootdir(), subfolder, 'PARC_' + template_fname)
        else:
            subfolder, runname = "", ""
            output_dname = os.path.join(utils.getrootdir(), 'PARC_' + template_fname)

        if not os.path.exists(output_dname):
            os.mkdir(output_dname)

        if configuration.verbose:
            ourPARC.verbose = True
        ourPARC.logger = utils.getLogger()

        ourPARC.out_dir = output_dname

        ourPARC.processingMode = configuration.cur_processing_mode

        if self.hasInputFromPort("ignoreNonOverlap"):
            ourPARC.ignoreNonOverlap = self.getInputFromPort("ignoreNonOverlap")

        key_inputs = utils.get_raster_files(template)
        for rasters_csv in self.forceGetInputListFromPort("RastersWithPARCInfoCSV"):
            key_inputs.append(rasters_csv.name)
        for predictor_list in self.forceGetInputListFromPort("PredictorList"):
            key_inputs.append(str(predictor_list))
        for predictor in self.forceGetInputListFromPort("predictor"):
            key_inputs.append(str(predictor))

        workingCSV, signature, already_run = utils.make_next_file_complex(self,
                                        prefix='PARCFiles', suffix='.csv',
                                        key_inputs=key_inputs,
                                        subfolder=os.path.join(subfolder, output_dname), runname=runname)


#          workingCSV = os.path.join(output_dname, "tmpFilesToPARC.csv")
        if already_run:
            writetolog("No change in inputs or paramaters using previous run of PARC", True)
        else:
            f = open(workingCSV, "wb")
            csvWriter = csv.writer(f)
            csvWriter.writerow(["FilePath", "Categorical", "Resampling", "Aggregation"])

            if self.hasInputFromPort("RastersWithPARCInfoCSV"):
                for input_rasters_csv in self.forceGetInputListFromPort('RastersWithPARCInfoCSV'):
                    csvReader = csv.reader(open(input_rasters_csv.name), delimiter=",")
                    header = csvReader.next()
                    for row in csvReader:
                        csvWriter.writerow([utils.getFileRelativeToCurrentVT(row[0]), row[1], row[2], row[3]])


            if self.hasInputFromPort("PredictorList"):
                predictor_lists = self.forceGetInputListFromPort('PredictorList')
                for predictor_list in predictor_lists:
                    for predictor in predictor_list:
                        csvWriter.writerow([utils.getFileRelativeToCurrentVT(predictor[0], self), predictor[1], predictor[2], predictor[3]])

            if self.hasInputFromPort("predictor"):
                predictor_list = self.forceGetInputListFromPort('predictor')
                for predictor in predictor_list:
                    csvWriter.writerow([utils.getFileRelativeToCurrentVT(predictor[0], self), predictor[1], predictor[2], predictor[3]])
            f.close()
            del csvWriter
            ourPARC.inputs_CSV = workingCSV
            ourPARC.template = template
            writetolog('    template layer = ' + template)
            writetolog("    output_dname=" + output_dname, False, False)
            writetolog("    workingCSV=" + workingCSV, False, False)
            try:
                ourPARC.parcFiles()
            except TrappedError as e:
                writetolog(e.message)
                raise ModuleError(self, e.message)
            except:
                utils.informative_untrapped_error(self, "PARC")

        utils.write_hash_entry_pickle(signature, workingCSV)
        output_file = utils.create_file_module(workingCSV, module=self)

        self.setResult('RastersWithPARCInfoCSV', output_file)

class Reclassifier(Module):
    '''
    '''
    __doc__ = GenModDoc.construct_module_doc('Reclassifier')

    _input_ports = [("inputRaster", "(edu.utah.sci.vistrails.basic:Path)"),
                    ('reclassFile', '(edu.utah.sci.vistrails.basic:File)'),
                    ('reclassFileContents', '(edu.utah.sci.vistrails.basic:String)'),
                    ('run_name_info', '(gov.usgs.sahm:OutputNameInfo:Other)')]

    _output_ports = [('outputRaster', '(edu.utah.sci.vistrails.basic:File)')]

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        writetolog("\nRunning Reclassifier", True)
        port_map = {'inputRaster':('inputRaster', utils.dir_path_value, False),
                    'reclassFile':('reclassFile', utils.dir_path_value, False),
                    'reclassFileContents':('reclassFileContents', None, False), }

        argsDict = utils.map_ports(self, port_map)

        run_name_info = self.forceGetInputFromPort('run_name_info', None)
        if run_name_info:
            subfolder = run_name_info.contents.get('subfolder_name', "")
            runname = run_name_info.contents.get('runname', "")
            if runname:
                output_dname = os.path.join(utils.getrootdir(), subfolder)
            else:
                output_dname = os.path.join(utils.getrootdir(), subfolder)
        else:
            subfolder, runname = "", ""
            output_dname = os.path.join(utils.getrootdir())

        from pySAHM.TiffProcessor import rasterReclassifier
        ourReclassifier = rasterReclassifier()
        ourReclassifier.inputFname = argsDict['inputRaster']

        if argsDict.has_key('reclassFileContents'):
            reclassFileName = utils.mknextfile("reclass", ".txt")
            reclassFile = open(reclassFileName, "w")
            reclassFile.write(self.forceGetInputFromPort('reclassFileContents'))
            reclassFile.close()
            ourReclassifier.reclassFName = reclassFileName
        elif argsDict.has_key('reclassFile'):
            ourReclassifier.reclassFName = argsDict['reclassFile']
        else:
            msg = "Neither a reclass File or reclassFileContents have been specified\n"
            msg += "One or the other must be provided."
            raise ModuleError(self, msg)

        ourReclassifier.outDir = utils.getrootdir()

        in_shortname = utils.getShortName(ourReclassifier.inputFname)

        out_fname, signature, already_run = utils.make_next_file_complex(self,
                                        prefix=in_shortname, suffix='.tif',
                                        key_inputs=[argsDict['inputRaster']],
                                        subfolder=subfolder, runname=runname)

        if not already_run:
            ourReclassifier.outName = out_fname
            ourReclassifier.run()
            utils.write_hash_entry_pickle(signature, out_fname)

        output_file = utils.create_file_module(out_fname, module=self)


#        writetolog("Finished running PARC", True)
        self.setResult('outputRaster', output_file)

class ReclassifierConfiguration(StandardModuleConfigurationWidget):
    #  FIXME add available_dict as parameter to allow config
    def __init__(self, module, controller, parent=None):

        StandardModuleConfigurationWidget.__init__(self, module, controller,
                                                   parent)
        self.setWindowTitle("Reclassification")
        self.build_gui()

        self.loadText()

    def build_gui(self):
        QtGui.QWidget.__init__(self)

        self.buttonSave = QtGui.QPushButton('Save', self)
        self.buttonReset = QtGui.QPushButton('Cancel', self)

        self.buttonSave.clicked.connect(self.handleSave)
        self.buttonReset.clicked.connect(self.handleReset)

        layout = QtGui.QVBoxLayout()
        self.textBox = QtGui.QTextEdit(self)

        layout.addWidget(self.textBox)

        buttonLayout = QtGui.QHBoxLayout()
        buttonLayout.addWidget(self.buttonSave)
        buttonLayout.addWidget(self.buttonReset)
        layout.addLayout(buttonLayout)
        self.setLayout(layout)

        self.path = None

    def getPortValue(self, portName):
        for i in xrange(self.module.getNumFunctions()):
            if self.module.functions[i].name == portName:
                return self.module.functions[i].params[0].strValue
        return None

    def handleSave(self):
        #  call this to save any current changes
        curStringValue = str(self.textBox.toPlainText())

        self.updateVisTrail(curStringValue)

    def handleReset(self):
        self.close()

#    def save(self):
#        with open(unicode(self.path), 'wb') as stream:
#            writer = csv.writer(stream)
#            #surely there is some cleaner way to get the header list!
#            header = [str(self.contents.horizontalHeaderItem(i).text())
#                    for i in range(self.contents.horizontalHeader().count())]
#            writer.writerow(header)
#            for row in range(self.contents.rowCount()):
#                rowdata = []
#                for column in range(self.contents.columnCount()):
#                    item = self.contents.item(row, column)
#                    if item is not None:
#                        rowdata.append(
#                            unicode(item.text()).encode('utf8'))
#                    else:
#                        rowdata.append('')
#                writer.writerow(rowdata)

    def updateVisTrail(self, strCurContents):
        self.controller.update_ports_and_functions(self.module.id,
                                           [], [], [("reclassFileContents", [strCurContents])])
        self.state_changed = False
        self.emit(QtCore.SIGNAL("stateChanged"))
        self.emit(QtCore.SIGNAL('doneConfigure'), self.module.id)

    def loadText(self):

        if self.getPortValue('reclassFileContents'):
            self.textBox.setText(self.getPortValue('reclassFileContents'))
        elif self.getPortValue('reclassFile'):
            curContents = open(self.getPortValue('reclassFile'), 'r').readlines()

class CategoricalToContinuous(Module):
    '''
    '''
#    __doc__ = GenModDoc.construct_module_doc('RasterFormatConverter')

    _input_ports = [("inputRaster", "(edu.utah.sci.vistrails.basic:File)"),
                    ('templateFile', '(gov.usgs.sahm:TemplateLayer:DataInput)'),
                    ]

    _output_ports = [('outputsPredictorListFile', '(gov.usgs.sahm:RastersWithPARCInfoCSV:Other)')]

#    @classmethod
#    def provide_input_port_documentation(cls, port_name):
#        return GenModDoc.construct_port_doc(cls, port_name, 'in')
#    @classmethod
#    def provide_output_port_documentation(cls, port_name):
#         return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        writetolog("\nCategoricalToContinuous", True)
        port_map = {'inputRaster':('inputRaster', utils.dir_path_value, True),
                    'templateFile':('templateFile', utils.dir_path_value, True)}

        argsDict = utils.map_ports(self, port_map)

        from pySAHM.TiffProcessor import categoricalToContinuousRasters
        ourC2C = categoricalToContinuousRasters()
        ourC2C.inputFname = argsDict['inputRaster']
        ourC2C.templateFName = argsDict['templateFile']
        shortName = SpatialUtilities.getRasterShortName(argsDict['inputRaster'])

        ourC2C.outDir = os.path.join(utils.getrootdir(), shortName + "_c2c")

        ourC2C.run()

        output_file = utils.create_file_module(ourC2C.outputPredictorsList, module=self)
        self.setResult('outputsPredictorListFile', output_file)

class RasterFormatConverter(Module):
    '''
    '''
    __doc__ = GenModDoc.construct_module_doc('RasterFormatConverter')

    #  configuration = []
    _input_ports = [("inputMDS", "(gov.usgs.sahm:MergedDataSet:Other)"),
                    ('inputDir', '(edu.utah.sci.vistrails.basic:Directory)'),
                    ('format', '(edu.utah.sci.vistrails.basic:String)'),
                    ('multipleCores', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["True"]', 'optional':True})]

    _output_ports = [('outputDir', '(edu.utah.sci.vistrails.basic:Directory)')]

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        writetolog("\nRunning TiffConverter", True)
        ourRFC = RFC.FormatConverter()
        if self.hasInputFromPort('inputMDS'):
            ourRFC.MDSFile = utils.getFileRelativeToCurrentVT(self.forceGetInputFromPort('inputMDS').name, self)
        elif self.hasInputFromPort('inputDir'):
            ourRFC.inputDir = utils.getFileRelativeToCurrentVT(self.forceGetInputFromPort('inputDir').name, self)

        if self.hasInputFromPort('format'):
            f = self.forceGetInputFromPort('format')
            if f == '':
                f = 'asc'
            ourRFC.format = f

        if self.hasInputFromPort("multipleCores"):
            if self.getInputFromPort("multipleCores"):
                ourRFC.multicores = "True"

        ourRFC.outputDir = utils.mknextdir(prefix='ConvertedRasters')
        if configuration.verbose:
            ourRFC.verbose = True
        ourRFC.logger = utils.getLogger()
        writetolog("    output directory = " + ourRFC.outputDir, False, False)

        try:
            ourRFC.run()
        except TrappedError as e:
            raise ModuleError(self, e.message)
        except:
            utils.informative_untrapped_error(self, "RasterFormatConverter")


        outputDir = utils.create_dir_module(ourRFC.outputDir)
        self.setResult('outputDir', outputDir)
        writetolog("\nFinished running TiffConverter", True)

class ModelEvaluationSplit(Module):
    '''
    '''
    __doc__ = GenModDoc.construct_module_doc('ModelEvaluationSplit')

    _input_ports = [("inputMDS", "(gov.usgs.sahm:MergedDataSet:Other)"),
                    ('trainingProportion', '(edu.utah.sci.vistrails.basic:Float)',
                        {'defaults':'["0.7"]'}),
                    ('Seed', '(edu.utah.sci.vistrails.basic:Integer)'),
                    ('run_name_info', '(gov.usgs.sahm:OutputNameInfo:Other)')]
    _output_ports = [("outputMDS", "(gov.usgs.sahm:MergedDataSet:Other)")]

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        writetolog("\nGenerating Model Evaluation split ", True)
        inputMDS = utils.getFileRelativeToCurrentVT(utils.dir_path_value(self.forceGetInputFromPort('inputMDS', [])), self)

        if self.hasInputFromPort('run_name_info'):
            runinfo = self.forceGetInputFromPort('run_name_info')
            subfolder = runinfo.contents.get('subfolder', "")
            runname = runinfo.contents.get('runname', "")
        else:
            subfolder, runname = utils.get_previous_run_info(inputMDS)

        global models_path

        #  args = "i=" + '"' + inputMDS + '"' + " o=" + '"' + outputMDS + '"'
        #  args += " rc=" + utils.MDSresponseCol(inputMDS)
        args = {'i': inputMDS,

                'rc': utils.MDSresponseCol(inputMDS)}
        if (self.hasInputFromPort("trainingProportion")):
            try:
                trainingProportion = float(self.getInputFromPort("trainingProportion"))
                if trainingProportion <= 0 or trainingProportion > 1:
                    raise ModuleError(self, "Train Proportion (trainProp) must be a number between 0 and 1 excluding 0")
                #  args += " p=" + str(trainingProportion)
                args['p'] = str(trainingProportion)
            except:
                raise ModuleError(self, "Train Proportion (trainProp) must be a number between 0 and 1 excluding 0")
        if (self.hasInputFromPort("RatioPresAbs")):
            try:
                RatioPresAbs = float(self.getInputFromPort("RatioPresAbs"))
                if RatioPresAbs <= 0:
                    raise ModuleError(self, "The ratio of presence to absence (RatioPresAbs) must be a number greater than 0")
                #  args += " m=" + str(trainingProportion)
                args['m'] = str(trainingProportion)
            except:
                raise ModuleError(self, "The ratio of presence to absence (RatioPresAbs) must be a number greater than 0")

        args['es'] = "TRUE"

        seed = utils.get_seed(self.forceGetInputFromPort("Seed", None))
        writetolog("    seed used for Split = " + str(seed))
        args['seed'] = str(seed)

        outputMDS, signature, already_run = utils.make_next_file_complex(self,
                                prefix='ModelEvaluationSplit', suffix='.csv',
                                key_inputs=[inputMDS],
                                subfolder=subfolder, runname=runname)
        args['o'] = outputMDS

        if not already_run:
            utils.run_R_script("TestTrainSplit.r", args, self, new_r_path=configuration.r_path)
            utils.write_hash_entry_pickle(signature, outputMDS)

        output_file = utils.create_file_module(outputMDS, module=self)
        writetolog("Finished Model Evaluation split ", True)
        self.setResult("outputMDS", output_file)

class ModelSelectionSplit(Module):
    '''
    ToDo: Marian to write
    '''
    __doc__ = GenModDoc.construct_module_doc('ModelSelectionSplit')

    _input_ports = [("inputMDS", "(gov.usgs.sahm:MergedDataSet:Other)"),
                    ('trainingProportion', '(edu.utah.sci.vistrails.basic:Float)',
                        {'defaults':'["0.7"]'}),
                    ('Seed', '(edu.utah.sci.vistrails.basic:Integer)'),
                    ('run_name_info', '(gov.usgs.sahm:OutputNameInfo:Other)', {'optional':True}), ]

    _output_ports = [("outputMDS", "(gov.usgs.sahm:MergedDataSet:Other)")]

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        writetolog("\nGenerating Model Selection split ", True)
        inputMDS = utils.getFileRelativeToCurrentVT(utils.dir_path_value(self.forceGetInputFromPort('inputMDS', []), self))

        if self.hasInputFromPort('run_name_info'):
            runinfo = self.forceGetInputFromPort('run_name_info')
            subfolder = runinfo.contents.get('subfolder', "")
            runname = runinfo.contents.get('runname', "")
        else:
            subfolder, runname = utils.get_previous_run_info(inputMDS)

        global models_path

        #  args = "i=" + '"' + inputMDS + '"' + " o=" + '"' + outputMDS + '"'
        #  args += " rc=" + utils.MDSresponseCol(inputMDS)
        args = {'i': inputMDS,
                'rc': utils.MDSresponseCol(inputMDS)}
        if (self.hasInputFromPort("trainingProportion")):
            try:
                trainingProportion = float(self.getInputFromPort("trainingProportion"))
                if trainingProportion <= 0 or trainingProportion > 1:
                    raise ModuleError(self, "Train Proportion (trainProp) must be a number between 0 and 1 excluding 0")
                #  args += " p=" + str(trainingProportion)
                args['p'] = str(trainingProportion)
            except:
                raise ModuleError(self, "Train Proportion (trainProp) must be a number between 0 and 1 excluding 0")
        if (self.hasInputFromPort("RatioPresAbs")):
            try:
                RatioPresAbs = float(self.getInputFromPort("RatioPresAbs"))
                if RatioPresAbs <= 0:
                    raise ModuleError(self, "The ratio of presence to absence (RatioPresAbs) must be a number greater than 0")
                #  args += " m=" + str(trainingProportion)
                args['m'] = trainingProportion
            except:
                raise ModuleError(self, "The ratio of presence to absence (RatioPresAbs) must be a number greater than 0")

        #  args += " es=FALSE"
        args['es'] = "FALSE"

        seed = utils.get_seed(self.forceGetInputFromPort("Seed", None))
        writetolog("    seed used for Split = " + str(seed))
        #  args += " seed=" + str(seed)
        args['seed'] = str(seed)

        outputMDS, signature, already_run = utils.make_next_file_complex(self,
                                prefix='modelSelectionSplit', suffix='.csv',
                                key_inputs=[inputMDS],
                                subfolder=subfolder, runname=runname)
        args['o'] = outputMDS

        if not already_run:
            utils.run_R_script("TestTrainSplit.r", args, self, new_r_path=configuration.r_path)

        output_file = utils.create_file_module(outputMDS, module=self)
        writetolog("Finished Model Selection split ", True)
        utils.write_hash_entry_pickle(signature, outputMDS)
        self.setResult("outputMDS", output_file)

class ModelSelectionCrossValidation(Module):
    '''
    ToDo: Marian to write
    '''
    __doc__ = GenModDoc.construct_module_doc('ModelSelectionCrossValidation')

    _input_ports = [("inputMDS", "(gov.usgs.sahm:MergedDataSet:Other)"),
                    ('nFolds', '(edu.utah.sci.vistrails.basic:Integer)',
                        {'defaults':'["10"]', 'optional':True}),
                    ('SpatialSplit', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["False"]', 'optional':False}),
                    ('Stratify', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["True"]', 'optional':True}),
                    ('Seed', '(edu.utah.sci.vistrails.basic:Integer)'),
                    ('run_name_info', '(gov.usgs.sahm:OutputNameInfo:Other)', {'optional':True}) ]
    _output_ports = [("outputMDS", "(gov.usgs.sahm:MergedDataSet:Other)")]

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        writetolog("\nGenerating Cross Validation split ", True)
        port_map = {'inputMDS':('i', utils.dir_path_value, True),
                    'nFolds':('nf', None, True),
                    'SpatialSplit':('spt', utils.R_boolean, False),
                    'Stratify':('stra', utils.R_boolean, True)}

        argsDict = utils.map_ports(self, port_map)

        if self.hasInputFromPort('run_name_info'):
            runinfo = self.forceGetInputFromPort('run_name_info')
            subfolder = runinfo.contents.get('subfolder', "")
            runname = runinfo.contents.get('runname', "")
        else:
            subfolder, runname = utils.get_previous_run_info(argsDict['i'])

        argsDict["rc"] = utils.MDSresponseCol(argsDict["i"])

        if argsDict["nf"] <= 0:
            raise ModuleError(self, "Number of Folds must be greater than 0")

        seed = utils.get_seed(self.forceGetInputFromPort("Seed", None))
        if not argsDict.has_key('spt'):
                argsDict['spt'] = 'FALSE'

        writetolog("    seed used for Split = " + str(seed))
        argsDict["seed"] = str(seed)
        outputMDS, signature, already_run = utils.make_next_file_complex(self,
                                prefix='modelSelectionCV', suffix='.csv',
                                key_inputs=[argsDict['i']],
                                subfolder=subfolder, runname=runname)
        argsDict["o"] = outputMDS

        if not already_run:
            utils.run_R_script("CrossValidationSplit.r", argsDict, self, new_r_path=configuration.r_path)

        output_file = utils.create_file_module(outputMDS, module=self)
        writetolog("Finished Cross Validation split ", True)
        utils.write_hash_entry_pickle(signature, outputMDS)
        self.setResult("outputMDS", output_file)


class CovariateCorrelationAndSelection(Module):
    '''
    '''
    __doc__ = GenModDoc.construct_module_doc('CovariateCorrelationAndSelection')

    _input_ports = [("inputMDS", "(gov.usgs.sahm:MergedDataSet:Other)"),
                    ('selectionName', '(edu.utah.sci.vistrails.basic:String)', {'defaults':'["initial"]'}),
                    ('ShowGUI', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["True"]'}),
                    ('numPlots', '(edu.utah.sci.vistrails.basic:Integer)', {'defaults':'["8"]', 'optional':True}),
                    ('minCor', '(edu.utah.sci.vistrails.basic:Float)', {'defaults':'["0.7"]', 'optional':True}),
                    ('corsWithHighest', '(edu.utah.sci.vistrails.basic:Boolean)', {'defaults':'["False"]', 'optional':True}),
                    ('Seed', '(edu.utah.sci.vistrails.basic:Integer)', {'defaults':'["{}"]'.format(utils.get_seed()), 'optional':True}),
                    ('run_name_info', '(gov.usgs.sahm:OutputNameInfo:Other)', {'optional':True}), ]
    _output_ports = [("outputMDS", "(gov.usgs.sahm:MergedDataSet:Other)")]

    @classmethod
    def provide_input_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'in')
    @classmethod
    def provide_output_port_documentation(cls, port_name):
        return GenModDoc.construct_port_doc(cls, port_name, 'out')

    def compute(self):
        writetolog("\nOpening Select Predictors Layers widget", True)

        port_map = {'inputMDS': ('inputMDS', None, True),
                    'selectionName': ('selectionName', None, True),
                    'ShowGUI': ('ShowGUI', None, True),
                    'numPlots': ('numPlots', None, False),
                    'minCor': ('minCor', None, False),
                    'corsWithHighest': ('corsWithHighest', utils.R_boolean, False),
                    'Seed': ('seed', utils.get_seed, True)}

        params = utils.map_ports(self, port_map)

        if self.hasInputFromPort('run_name_info'):
            runinfo = self.forceGetInputFromPort('run_name_info')
            subfolder = runinfo.contents.get('subfolder', "")
            runname = runinfo.contents.get('runname', "")
        else:
            subfolder, runname = utils.get_previous_run_info(params['inputMDS'])

        if runname:
            runname = runname + "_" + params['selectionName']
        else:
            runname = params['selectionName']

        writetolog("    seed used for subsampling = " + str(params['seed']))
        global session_dir

        outfname = os.path.join(session_dir, subfolder, "CovariateCorrelationOutputMDS_" + runname + ".csv")
#          outputMDS, signature, already_run = utils.make_next_file_complex(self,
#                                  prefix="CovariateCorrelationOutputMDS_" + runname, suffix='.csv',
#                                  key_inputs=[params['inputMDS']],
#                                  subfolder=subfolder, runname=runname)
        if outfname == params['inputMDS']:
            outfname = outfname[:-4] + "_2.csv"

        params['outputMDS'] = outfname
        params['displayJPEG'] = os.path.join(session_dir, subfolder, "CovariateCorrelationDisplay.png")
        params['r_path'] = configuration.r_path
        params['module'] = self
        writetolog("    inputMDS = " + params['inputMDS'], False, False)
        writetolog("    displayJPEG = " + params['displayJPEG'], False, False)
        writetolog("    outputMDS = " + params['outputMDS'], False, False)

        if os.path.exists(params['outputMDS']) and params['ShowGUI']:
            utils.applyMDS_selection(params['outputMDS'], params['inputMDS'])
            os.remove(params['outputMDS'])
            self.callDisplayMDS(params)
        elif os.path.exists(params['outputMDS']) and not params['ShowGUI']:
            utils.applyMDS_selection(params['outputMDS'], params['inputMDS'])
            os.remove(params['outputMDS'])
            shutil.copy2(params['inputMDS'], params['outputMDS'])
            writetolog("    Applying previous selection but not showing GUI", False, True)
        else:
            self.callDisplayMDS(params)


        output_file = utils.create_file_module(params['outputMDS'], module=self)
        writetolog("Finished Select Predictors Layers widget", True)
        self.setResult("outputMDS", output_file)

    def callDisplayMDS(self, kwargs):
        dialog = SelectListDialog(kwargs)
        #  dialog.setWindowFlags(QtCore.Qt.WindowMaximizeButtonHint)
        retVal = dialog.exec_()
        #  outputPredictorList = dialog.outputList
        if retVal == 1:
            raise ModuleError(self, "Cancel or Close selected (not OK) workflow halted.")


#  class ProjectionLayers(Module):
#    '''
#    Projection Layers
#
#    Note: as of June 2011, this module offers some functionality that is only available
#    to users running the SAHM package within the USGS Fort Collins Science Center (FORT).
#
#    The ProjectionLayers module provides the option to prepare a separate set of predictor
#    layers so that the results of a model developed from one set of environmental predictors
#    can be projected onto a new modeled space. This second set of environmental predictors
#    (corresponding to the "projection target") most often contains the same environmental
#    predictors but represents data captured at a different temporal or spatial location. For
#    example, a user could generate a model predicting habitat suitability using recorded
#    presence points and certain environmental predictors such as elevation, landcover, and
#    proximity to water in one geographic location. Based on the training from this information,
#    the modeled results could be generated for (or "projected to") a new location based on the
#    range of values seen in elevation, landcover, and proximity to water in the second geographic
#    area. Similarly, modeling predicted results through time is also possible. A model trained
#    using field data and a set of predictor layers representative of one time period could be
#    projected onto the same geographical area using a new set of predictor layers corresponding
#    to the same predictors but representing data from a different time period (e.g., different
#    climate data).
#
#    The output of this module is subsequently used as the projection target in the ApplyModel module.
#
#    (As part of the process of preparing the layers for modeling, the ProjectionLayers module runs
#    the PARC module internally on the inputs. Outputs from the ProjectionLayers module will possess
#    matching coordinate systems, cell sizes, and extents and do not need to be run through PARC
#    before being used downstream in the workflow.)
#
#    Six parameters can be set by the user:
#
#    1. Directory Crosswalk CSV: This is a .csv file containing two columns designating
#    the layers that should be swapped out in the projected model. The first column
#    contains a list of the full paths to the predictor layers used to develop the original
#    model that will be replaced in the projection process. The second column contains the
#    full paths to the new predictor layers that will substitute the respective layers used
#    in the original model. Each original layer in the first column should be paired with
#    its replacement in the second column (e.g., Column 1 = C:\ModelLayers\Precipitation1980.tif,
#    Column 2 = C:\ModelLayers\Precipitation2000.tif). In the case of any file used to develop
#    the first model that is not expressly listed in the Directory Crosswalk CSV with a
#    replacement, the original file will be used in the new model projection. The module
#    anticipates a header row in this .csv file (thus, the first row of data will be ignored).
#
#    2. File List CSV: This is a .csv file containing the list of predictor files used to
#    develop the first model. Effectively, this file will be updated based on the information
#    provided in the directory crosswalk .csv and used as the input to the training process
#    for the projected model. The output of the PARC module from the first model iteration
#    should be used as the input to this parameter.
#        '''
#    _input_ports = [('RastersWithPARCInfoCSV', '(gov.usgs.sahm:RastersWithPARCInfoCSV:Other)'),
#                    ('templateLayer', '(gov.usgs.sahm:TemplateLayer:DataInput)'),
#                    ('directoryCrosswalkCSV', '(edu.utah.sci.vistrails.basic:File)')
#                    ]
#    _output_ports = [("MDS", "(gov.usgs.sahm:MergedDataSet:Other)")]
#
#    def compute(self):
#
#        writetolog("\nRunning make Projection Layers", True)
#
#        inputCSV = utils.getFileRelativeToCurrentVT(self.forceGetInputFromPort('RastersWithPARCInfoCSV').name, self)
#
#        template = self.forceGetInputFromPort('templateLayer', '')
#        fromto = []
#
#        if self.hasInputFromPort('directoryCrosswalkCSV'):
#            crosswalkCSVFname = utils.getFileRelativeToCurrentVT(self.forceGetInputFromPort('directoryCrosswalkCSV'), self)
#            crosswalkCSV = csv.reader(open(crosswalkCSVFname, 'r'))
#            header = crosswalkCSV.next()
#            fromto = []
#            for row in crosswalkCSV:
#                fromto.append(row[0], row[1])
#            del crosswalkCSV
#
#        if self.hasInputFromPort('templateLayer'):
#            template = utils.getFileRelativeToCurrentVT(self.forceGetInputFromPort('templateLayer'), self)
#        else:
#            template = ''
#
#        #write out the outputs to an empty MDS file (just the header is needed to PARC the outputs)
#        inCSV = csv.reader(open(inputCSV, 'r'))
#        inCSV.next() #skip header
#        workingCSV = utils.mknextfile(prefix='tmpFilesToPARC_', suffix='.csv')
#        tmpCSV = csv.writer(open(workingCSV, 'wb'))
#        tmpCSV.writerow(["FilePath", "Categorical", "Resampling", "Aggregation"])
#        outHeader1 = ['X', 'Y', 'response']
#        outHeader2 = ['', '', '']
#        outHeader3 = ['', '', '']
#
#        output_dname = utils.mknextdir(prefix='ProjectionLayers_')
#
#        for row in inCSV:
#            if template == '':
#                template = row[0]
#            fileShortName = utils.getShortName(row[0])
#            if row[1] == 1:
#                outHeader1.append(fileShortName + '_categorical')
#            else:
#                outHeader1.append(fileShortName)
#            outHeader2.append('1')
#            outHeader3.append(os.path.join(output_dname, fileShortName + '.tif'))
#
#            origFile = row[4]
#            newOrigFile = origFile
#            for lookup in fromto:
#                if lookup[0] in origFile:
#                    newOrigFile = origFile.replace(lookup[0], lookup[1])
#            tmpCSV.writerow([newOrigFile,] + row[1:4])
#        del tmpCSV
#
#        #PARC the files here
#        ourPARC = parc.PARC()
#
#
#        if configuration.verbose:
#            ourPARC.verbose = True
#        writetolog("    output_dname=" + output_dname, False, False)
#        ourPARC.outDir = output_dname
#        ourPARC.inputsCSV = workingCSV
#        ourPARC.template = template
#
#        try:
#            ourPARC.parcFiles()
#        except TrappedError as e:
#            raise ModuleError(self, e.message)
#        except :
#            utils.informative_untrapped_error(self, "PARC")
#
#        #loop through our workingCSV and format it into an MDS header
#
#        #outputMDS = utils.mknextfile(prefix='ProjectionLayersMDS_', suffix = '.csv')
#        outputMDS = os.path.join(output_dname, 'ProjectionLayersMDS.csv')
#        outCSV = csv.writer(open(outputMDS, 'wb'))
#        outCSV.writerow(outHeader1)
#        outCSV.writerow(outHeader2)
#        outCSV.writerow(outHeader3)
#
#        output_file = utils.create_file_module(outputMDS, module=self)
#        self.setResult("MDS", output_file)
#        writetolog("Finished Select Projection Layers widget", True)




def load_max_ent_params():
    maxent_fname = os.path.join(os.path.dirname(__file__), 'maxent.csv')
    csv_reader = csv.reader(open(maxent_fname, 'rU'))
    #  pass on header
    csv_reader.next()
    input_ports = list(MAXENT._input_ports)

    docs = {}
    basic_pkg = 'edu.utah.sci.vistrails.basic'
    for row in csv_reader:
        [name, flag, p_type, default, doc, notes] = row
        name = name.strip()
        p_type = p_type.strip()
        kwargs = {}
        default = default.strip()
        if default:
            default = eval(default)
            kwargs['defaults'] = str([str(default)])
        if p_type == 'Boolean':
            kwargs['optional'] = True
        input_ports.append((name, '(' + basic_pkg + ':' + p_type + ')', kwargs))
        docs[name] = doc


    #  print 'MAXENT:', input_ports
    MAXENT._input_ports = input_ports
    MAXENT._port_docs = docs

    def provide_input_port_documentation(cls, port_name):
        return cls._port_docs[port_name]
    MAXENT.provide_input_port_documentation = \
        classmethod(provide_input_port_documentation)

def initialize():

    global maxent_path, java_path, color_breaks_csv
    global session_dir

    session_dir = configuration.cur_session_folder
    if not os.path.exists(session_dir):
        import tempfile
        orig_session_dir = session_dir
        session_dir = tempfile.mkdtemp(prefix="SAHM_session_dir_")
        utils.createLogger(session_dir, configuration.verbose)
        writetolog("!" * 79)
        writetolog("The previous session directory: " + orig_session_dir + " no longer exists on the file system!")
        writetolog("Defaulting to a random temporary location: " + session_dir)
        writetolog("!" * 79)

    utils.setrootdir(session_dir)
    utils.importOSGEO()
    utils.createLogger(session_dir, configuration.verbose)

    utils.set_r_path(configuration.r_path)
    if not os.path.exists(utils.get_r_path()) and \
        system.systemType in ['Microsoft', 'Windows']:
        #  they don't have a decent R path, let's see if we can pull one from the
        utils.set_r_path(utils.pull_R_install_from_reg())
        configuration.r_path = utils.get_r_path()
        package_manager = get_package_manager()
        package = package_manager.get_package(identifier)
        dom, element = package.find_own_dom_element()
        configuration.write_to_dom(dom, element)

    try:
        testfname = os.path.join(utils.get_r_path(), "CanSAHMWriteToR.txt")
        open(testfname, "wb")
        os.remove(testfname)
    except:
        msg = ("!"*79 + "\n") * 3
        msg += "The current directory that R  is installed in:\n\t"
        msg += utils.get_r_path()
        msg += "\nIs not writeable!  This will cause errors in the\n"
        msg += "R modules unless all required packages are already installed!!!\n"
        msg += "Either point to an installation of R that is writeable or \n"
        msg += "Run VisTrails as administrator until all R packages have been downloaded.\n"
        msg += "\n  See page 3 of the user manual for more information!\n"
        msg += ("!"*79 + "\n") * 3
        writetolog(msg, True, True)


    maxent_path = os.path.abspath(configuration.maxent_path)
    if not os.path.exists(maxent_path) and os.path.exists(r"C:\Maxent\maxent.jar"):
        maxent_path = r"C:\Maxent"
        configuration.maxent_path = maxent_path
    if not os.path.exists(maxent_path) and maxent_path == r"..\\..\\Central_Maxent":
        maxent_path = r"C:\Maxent\maxent.jar"

    if not os.path.exists(maxent_path):
        msg = ("!"*79 + "\n") * 3
        msg += "The current installation of Maxent could not be found:\n\t"
        msg += maxent_path
        msg += "\nThe Maxent model will not work until this has been set correctly!\n"
        msg += "\n  See page 5 of the user manual for more information!\n"
        msg += ("!"*79 + "\n") * 3
        writetolog(msg, True, True)

    java_path = utils.find_java_exe(configuration.java_path)

    utils.set_seed(configuration.default_seed)

    gdal_data = os.path.join(os.path.dirname(__file__), "GDAL_Resources", "gdal-data")
    os.environ['GDAL_DATA'] = gdal_data
    projlib = os.path.join(os.path.dirname(__file__), "GDAL_Resources", "projlib")
    os.environ['PROJ_LIB'] = projlib

    color_breaks_csv = os.path.abspath(os.path.join(os.path.dirname(__file__), "ColorBreaks.csv"))

    load_max_ent_params()

    utilities.storeUNCDrives()
    utilities.start_new_pool(utilities.get_process_count(configuration.cur_processing_mode))

    global layers_csv_fname

    writetolog("*" * 79)
    writetolog("Initializing:", True, True)
    writetolog("  Locations of dependencies")
#    writetolog("   Layers CSV = " + os.path.join(os.path.dirname(__file__), 'layers.csv'))
    writetolog("   Layers CSV = " + layers_csv_fname)
    writetolog("   R path = " + utils.get_r_path())
    writetolog("   Maxent folder = " + maxent_path)
#    writetolog("   QGIS folder = " + os.path.abspath(configuration.qgis_path))
#    writetolog("        Must contain subfolders qgis1.7.0, OSGeo4W")
    writetolog("    ")
    writetolog("*" * 79)
    writetolog("*" * 79)
    writetolog("SAHM output directory:   " + session_dir)
    writetolog("*" * 79)
    writetolog("*" * 79)

def finalize():
    pass

def generate_namespaces(modules):
    module_list = []
    for namespace, m_list in modules.iteritems():
        for module in m_list:
            m_dict = {'namespace': namespace}
            if type(module) == tuple:
                m_dict.update(module[1])
                module_list.append((module[0], m_dict))
                #  print 'm_dict:', m_dict
            else:
                module_list.append((module, m_dict))
    return module_list

def build_available_trees():
    trees = {}
    global layers_csv_fname
    layers_csv_fname = os.path.join(os.path.dirname(__file__), 'layers.csv')
    csv_reader = csv.reader(open(layers_csv_fname, 'rU'))
    csv_reader.next()
    first_file = csv_reader.next()[0]

    #  if the first file in the layers file does not exist assume that none
    #  of them do and use the exampledata version
    global atFORT
    if not os.path.exists(first_file):
        print (("!" * 30) + " WARNING " + ("!" * 30) + "\n") * 3
        print "The first grid in your layers CSV could not be found."
        print "Defaulting to the example data csv."
        print "fix/set paths in file " + layers_csv_fname + " to enable this functionality."
        print "See documentation for more information on setting up the layers.csv\n"
        print (("!" * 30) + " WARNING " + ("!" * 30) + "\n") * 3
        layers_csv_fname = os.path.join(os.path.dirname(__file__), 'layers.exampledata.csv')
        atFORT = False

    else:
        atFORT = True

#    #####Only for testing tutorial data
#    print "For tutorial tesing uing the layers.exampledata.csv"
#    layers_csv_fname = os.path.join(os.path.dirname(__file__), 'layers.exampledata.csv')

    csv_reader = csv.reader(open(layers_csv_fname, 'rU'))
    #  pass on header
    csv_reader.next()
    for row in csv_reader:
        if row[2] not in trees:
            trees[row[2]] = {}
        available_dict = trees[row[2]]
        if row[3] not in available_dict:
            available_dict[row[3]] = []
        available_dict[row[3]].append((row[0], row[1], row[4]))

    return trees

def build_predictor_modules():
    available_trees = build_available_trees()
    modules = []
    for name, tree in available_trees.iteritems():
        name_arr = name.strip().split()
        class_base = ''.join(n.capitalize() for n in name_arr)
        widget_class = get_predictor_widget(class_base, tree)
        config_class = get_predictor_config(class_base, tree)
        class_name = class_base + "Predictors"
        def get_widget_method(w_class):
            @staticmethod
            def get_widget_class():
                return w_class
            return get_widget_class
        module = type(class_name, (PredictorList,),
                      {'get_widget_class': get_widget_method(widget_class),
                       '_input_ports': \
                           [('value',
                             '(gov.usgs.sahm:%s:DataInput)' % class_name, True)]})
        modules.append((module, {'configureWidgetType': config_class,
                                 'moduleColor':INPUT_COLOR,
                                 'moduleFringe':INPUT_FRINGE}))
    for module in modules:
        module[0]._output_ports.append(('value_as_string', '(edu.utah.sci.vistrails.basic:String)', True))

    return modules

###################################
class TextFile(File):
    pass

class TextFileConfiguration(StandardModuleConfigurationWidget):
    #  FIXME add available_dict as parameter to allow config
    def __init__(self, module, controller, contents=None,
                 filter='', parent=None):
        StandardModuleConfigurationWidget.__init__(self, module, controller,
                                                   parent)
        self.fileFilter = filter

        if contents:
            self.contents = contents
        else:
            self.contents = QtGui.QTextEdit(self)

        self.setWindowTitle("Text File")
        self.build_gui()

        fid = self.findSourceFunction()
        if fid != -1:
            f = self.module.functions[fid]
            self.path = f.params[0].strValue
            self.loadText()

    def findSourceFunction(self):
        fid = -1
        for i in xrange(self.module.getNumFunctions()):
            if self.module.functions[i].name == "value":
                fid = i
                break
        return fid

    def build_gui(self):
        QtGui.QWidget.__init__(self)

        self.buttonOpen = QtGui.QPushButton('Open', self)
        self.buttonSave = QtGui.QPushButton('Save', self)
        self.buttonSaveAs = QtGui.QPushButton('Save As...', self)
        self.buttonReset = QtGui.QPushButton('Cancel', self)

        self.buttonOpen.clicked.connect(self.handleOpen)
        self.buttonSave.clicked.connect(self.handleSave)
        self.buttonSaveAs.clicked.connect(self.handleSaveAs)
        self.buttonReset.clicked.connect(self.handleReset)

        layout = QtGui.QVBoxLayout()
        layout.addWidget(self.contents)
        buttonLayout = QtGui.QHBoxLayout()
        buttonLayout.addWidget(self.buttonOpen)
        buttonLayout.addWidget(self.buttonSave)
        buttonLayout.addWidget(self.buttonSaveAs)
        buttonLayout.addWidget(self.buttonReset)
        layout.addLayout(buttonLayout)
        self.setLayout(layout)

        self.path = ''

    def handleReset(self):
        self.loadText()

    def handleSave(self):
        if not os.path.exists(self.path):
            self.path = QtGui.QFileDialog.getSaveFileName(
                self, 'Save File', os.path.split(self.path)[0], self.fileFilter)
        if not self.path.isEmpty():
            self.save()

    def save(self):
        f = open(self.path, "w")
        f.write(self.contents.toPlainText())

    def handleSaveAs(self):
        self.path = QtGui.QFileDialog.getSaveFileName(
                self, 'Save File As', os.path.split(self.path)[0], self.fileFilter)

        if not self.path.isEmpty():
            tmp = open(self.path, "w")
            del tmp
            self.handleSave()
            self.updateVisTrail()

    def updateVisTrail(self):
        self.controller.update_ports_and_functions(self.module.id,
                                           [], [], [("value", [str(self.path)])])
        self.state_changed = False
        self.emit(QtCore.SIGNAL("stateChanged"))
        self.emit(QtCore.SIGNAL('doneConfigure'), self.module.id)

    def handleOpen(self):
        self.path = QtGui.QFileDialog.getOpenFileName(
                self, 'Open File', os.path.split(self.path)[0], '')
        if not self.path.isEmpty():
            self.loadText()
            self.updateVisTrail()

    def loadText(self):
        f = open(self.path, 'r')
        data = f.read()
        self.contents.setText(data)

class CSVTextFile(TextFile):
    pass

class CSVTextFileConfiguration(TextFileConfiguration):
    #  FIXME add available_dict as parameter to allow config
    def __init__(self, module, controller, parent=None):

        fileFilter = 'CSV(*.csv)'
        contents = QtGui.QTableWidget(0, 0)
        TextFileConfiguration.__init__(self, module, controller, contents,
                                            fileFilter, parent)

        self.setWindowTitle("CSV Text File")


    def save(self):
         with open(unicode(self.path), 'wb') as stream:
            writer = csv.writer(stream)
            #  surely there is some cleaner way to get the header list!
            header = [str(self.contents.horizontalHeaderItem(i).text()) for i in
                      range(self.contents.horizontalHeader().count())]
            writer.writerow(header)
            for row in range(self.contents.rowCount()):
                rowdata = []
                for column in range(self.contents.columnCount()):
                    item = self.contents.item(row, column)
                    if item is not None:
                        rowdata.append(
                            unicode(item.text()).encode('utf8'))
                    else:
                        rowdata.append('')
                writer.writerow(rowdata)

    def loadText(self):
        with open(unicode(self.path), 'rb') as stream:
            csvReader = csv.reader(stream)
            header = csvReader.next()
            self.contents.setRowCount(0)
            self.contents.setColumnCount(len(header))
            self.contents.setHorizontalHeaderLabels(header)

            for rowdata in csvReader:
                row = self.contents.rowCount()
                self.contents.insertRow(row)
                self.contents.setColumnCount(len(rowdata))
                for column, data in enumerate(rowdata):
                    item = QtGui.QTableWidgetItem(data.decode('utf8'))
                    self.contents.setItem(row, column, item)

###################################

INPUT_COLOR = (0.76, 0.76, 0.8)
INPUT_FRINGE = [(0.0, 0.0),
                    (0.25, 0.0),
                    (0.0, 1.0)]

model_color = (0.76, 0.8, 0.76)
model_fringe = [(0.0, 0.0),
                    (0.25, 0.5),
                    (0.0, 1.0)]

output_color = (0.8, 0.8, 0.76)
output_fringe = [(0.0, 0.0),
                    (0.25, 0.0),
                    (0.0, 1.0)]

_modules = generate_namespaces({'DataInput': [
                                              (Predictor, {'moduleColor':INPUT_COLOR,
                                                           'moduleFringe':INPUT_FRINGE}),
                                              (PredictorListFile, {'moduleColor':INPUT_COLOR,
                                                           'moduleFringe':INPUT_FRINGE}),
                                              (FieldData, {'moduleColor':INPUT_COLOR,
                                                           'moduleFringe':INPUT_FRINGE}),
                                               (TemplateLayer, {'moduleColor':INPUT_COLOR,
                                                           'moduleFringe':INPUT_FRINGE}), ] + \
                                              build_predictor_modules(),
                                'Tools': [FieldDataQuery,
                                          FieldDataAggregateAndWeight,
                                          MDSBuilder,
#                                          MDSBuilder_vector,
                                          PARC,
                                          RasterFormatConverter,
#                                          ProjectionLayers,
                                          ModelEvaluationSplit,
                                          ModelSelectionSplit,
                                          ModelSelectionCrossValidation,
                                          CovariateCorrelationAndSelection,
                                          ApplyModel,
                                          BackgroundSurfaceGenerator,
                                          OutputName
                                          ],
                                'GeospatialTools': [(Reclassifier, {'configureWidgetType': ReclassifierConfiguration}),
                                                    CategoricalToContinuous,
                                                    (GeoSpatialViewerCell, {'moduleColor':output_color,
                                                           'moduleFringe':output_fringe}),
                                                    (RasterLayer, {'moduleColor':INPUT_COLOR,
                                                           'moduleFringe':INPUT_FRINGE}),
                                                    (PolyLayer, {'moduleColor':INPUT_COLOR,
                                                           'moduleFringe':INPUT_FRINGE}),
                                                    (PointLayer, {'moduleColor':INPUT_COLOR,
                                                           'moduleFringe':INPUT_FRINGE}),
#                                                      (LineLayer, {'moduleColor':INPUT_COLOR,
#                                                             'moduleFringe':INPUT_FRINGE}),
                                                    ],
                                'Models': [(GLM, {'moduleColor':model_color,
                                                           'moduleFringe':model_fringe}),
                                           (RandomForest, {'moduleColor':model_color,
                                                           'moduleFringe':model_fringe}),
                                           (MARS, {'moduleColor':model_color,
                                                           'moduleFringe':model_fringe}),
                                           (MAXENT, {'moduleColor':model_color,
                                                           'moduleFringe':model_fringe}),
                                           (BoostedRegressionTree,
                                                {
                                                 'moduleColor':model_color,
                                                           'moduleFringe':model_fringe}),
                                           (HabitatSuitabilityCurve,
                                                {
                                                 'moduleColor':model_color,
                                                           'moduleFringe':model_fringe}),
                                           ],
                                'Other':  [(Model, {'abstract': True}),
                                           (VectorLayer, {'abstract': True}),
                                           (ResampleMethod, {'abstract': True}),
                                           (AggregationMethod, {'abstract': True}),
                                           (PredictorList, {'abstract': True}),
                                           (MergedDataSet, {'abstract': True}),
                                           (ResponseType, {'abstract': True}),
                                           (RastersWithPARCInfoCSV, {'abstract': True}),
                                           (PointAggregationMethod, {'abstract': True}),
                                           (ModelOutputType, {'abstract': True}),
                                           (RandomPointType, {'abstract': True}),
                                           (OutputRaster, {'abstract': True}),
                                           (mpl_colormap, {'abstract': True}),
                                           (T_O_M, {'abstract': True}),
                                           (BaseGeoViewerCell, {'abstract': True}),
                                           (OutputNameInfo, {'abstract': True}),
#                                           (TextFile, {'configureWidgetType': TextFileConfiguration}),
#                                           (CSVTextFile, {'configureWidgetType': CSVTextFileConfiguration})
                                           ],
                                'Output': [(SAHMModelOutputViewerCell, {'moduleColor':output_color,
                                                           'moduleFringe':output_fringe}),
                                          (SAHMSpatialOutputViewerCell, {'moduleColor':output_color,
                                                           'moduleFringe':output_fringe}),
#                                             (GeneralSpatialViewer, {'moduleColor':output_color,
#                                                             'moduleFringe':output_fringe}),
#                                             (PointShapefile, {'moduleColor':output_color,
#                                                             'moduleFringe':output_fringe}),
#                                            (PolyShapefile, {'moduleColor':output_color,
#                                                            'moduleFringe':output_fringe}),  #not ready for prime time yet
                                          ]
                                })

def handle_module_upgrade_request(controller, module_id, pipeline):
    module_remap = {'Tools|BackgroundSurfaceGenerator':
                     [(None, '1.0.2', 'Tools|BackgroundSurfaceGenerator',
                          {'dst_port_remap': {'bias': 'continuous'} })],
                    'Tools|MDSBuilder':
                     [(None, '1.0.2', 'Tools|MDSBuilder',
                          {'dst_port_remap': {'backgroundpointCount': 'backgroundPointCount', } }),
                      (None, '1.2.0', 'Tools|MDSBuilder',
                          {'dst_port_remap': {'backgroundPointType':None, } })],
                    'Tools|PARC':
                     [(None, '1.0.2', 'Tools|PARC',
                          {'dst_port_remap': {'bias': '',
                                              'multipleCores': '', } })],
                    'Tools|RasterFormatConverter':
                    [(None, '1.0.2', 'Tools|RasterFormatConverter',
                          {'dst_port_remap': {'multipleCores': '', } })],
                    'Models|MAXENT':
                    [(None, '1.0.2', 'Models|MAXENT',
                          {'dst_port_remap': {'inputMDS': 'mdsFile', } })],
                    }
    for m in ['GLM', 'MARS', 'RandomForest', 'BoostedRegressionTree']:
        module_remap['Models|' + m] = [(None, '1.0.2', 'Models|' + m,
                          {'dst_port_remap': {'modelWorkspace': utils.getParentDir} }),
                                       (None, '1.2.0', 'Models|' + m,
                          {'function_remap': {'ThresholdOptimizationMethod': utils.convert_tom} })]

    module_remap['Models|MARS'].append((None, '1.2.0', 'Models|MARS',
                          {'dst_port_remap': {'MarsPenalty': 'MarsPenalty'} }))

    for m in ['ApplyModel']:
        module_remap['Tools|' + m] = [(None, '1.0.1', 'Tools|' + m,
                          {'dst_port_remap': {'modelWorkspace': utils.getParentDir} })]

    module_remap['Output|SAHMSpatialOutputViewerCell'] = [(None, '1.0.2', 'Output|SAHMSpatialOutputViewerCell',
                          {'dst_port_remap': {'model_workspace': utils.getParentDir} })]
    module_remap['Output|SAHMModelOutputViewerCell'] = [(None, '1.0.2', 'Output|SAHMModelOutputViewerCell',
                          {'dst_port_remap': {'ModelWorkspace': utils.getParentDir} })]
#
#    for m in ['SAHMSpatialOutputViewerCell', 'SAHMModelOutputViewerCell']:
#        module_remap['Output|' + m] = [(None, '1.0.2', 'Output|' + m,
#                          {'src_port_remap': {'model_workspace': 'ModelWorkspace',
#                                              'modelWorkspace': utils.getParentDir} })]

    return UpgradeWorkflowHandler.remap_module(controller, module_id, pipeline,
                                             module_remap)
