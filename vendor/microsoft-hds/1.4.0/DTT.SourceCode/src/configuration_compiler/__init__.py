# update sys.path so configuration_compiler can import directly from its own libs
import os
from pathlib import Path
import sys


path_to_add = os.fspath(Path(__file__).parent.parent) 
# path_ro_add is now the path to the configuration_compiler parent folder
# in dev it is <...>/CRM.ICS.AI.DMF.VsCodeExtension/bundled/tool/dtt_ext
# if this package is deployed as a wheel, it is <python env>/lib/python3.10/site-packages
sys.path.insert(0, path_to_add)