# ========================================================
# Simulink-Python binding generator
# Generator author: Yuxuan Jiang
# Tested by: Guojian Zhan & Yuxuan Jiang
# Based on code generated by MathWorks Embedded Coder®
# ========================================================

import os
import json
from contextlib import contextmanager
from enum import Enum
import pathlib
import shutil
from functools import reduce

# TODO: Use aligned numpy type directly get it in cython?
# TODO: Proper obs and action space

MODEL_SOURCE_INJECTIONS = "#define {0} {0}__actual\n"
MODEL_HEADER_INJECTIONS = "{0} {1}__actual = {2}::{1};\n"
TYPE_MAPPING = {
    "uint8": "stdint.uint8_t",
    "logical": "stdint.uint8_t",
    "": "void*",  # TODO: better pointer support
    # TODO: more types
}

NP_TYPE_MAPPING = {
    "stdint.uint8_t": "uint8_t",
    "double": "double_t"
    # TODO: more types
}

PY_TYPE_MAPPING = {
    "stdint.uint8_t": "int",
    "double": "float"
    # TODO: more types, logical support?
}

PY_NP_TYPE_MAPPING = {
    "stdint.uint8_t": "np.uint",
    "double": "np.double"
    # TODO: more types
}


def arrayify(inp):
    if isinstance(inp, list):
        return inp
    else:
        return [inp]


def write_text_safe(path: pathlib.Path, text: str):
    if path.exists():
        import time
        path.rename(path.with_name(f"{path.name}_backup_{time.strftime('%H-%M-%S')}{path.suffix}"))
    path.write_text(text, encoding='utf-8')


class Types(Enum):
    SCALAR = 1
    ARRAY = 2
    STRUCT = 3


class WriterContext:
    DIRECTIVES = [
        "# cython: language_level=3",
        "# distutils: language = c++",
    ]

    BANNER = [
        "# ========================================================",
        "# Generated with SPBG (Simulink-Python binding generator)",
        "# Generator author: Yuxuan Jiang",
        "# Tested by: Guojian Zhan & Yuxuan Jiang",
        "# Based on code generated by MathWorks Embedded Coder®",
        "# ========================================================",
    ]

    CIMPORTS = [
        "from libc cimport stdint",
        "import numpy as np",
        "cimport numpy as np",
        "from cpython cimport array",
    ]

    TEMPLATE_EXTERN = "cdef extern from '{header}':"
    TEMPLATE_CTYPEDEF_GENERIC = "ctypedef {type} {name};"
    TEMPLATE_CTYPEDEF_ARRAY = "ctypedef {type}[{size}] {name};"
    TEMPLATE_CTYPEDEF_STRUCT = "ctypedef struct {name}:"
    TEMPLATE_STRUCT = "struct {name}:"
    TEMPLATE_SCALAR = "{type} {name};"
    TEMPLATE_VECTOR = "{type} {name}[{size}];"
    TEMPLATE_CDEF_CLASS = "cdef cppclass {name}:"
    TEMPLATE_CTOR = "{name}({args}) except +"
    TEMPLATE_METHOD = "{ret} {name}({args})"  # TODO: modifiers?
    TEMPLATE_FIELD = "{type} {name};"

    TEMPLATE_CIMPORT = "from {path} cimport {name}"
    TEMPLATE_IMPORT = "from {path} import {name}"
    TEMPLATE_WRAPPER_STATIC = "@staticmethod"
    TEMPLATE_WRAPPER_METHOD = "def {name}({args}):"
    TEMPLATE_WRAPPER_CDEF = "cdef {ret} {name}(self, {args}):"
    TEMPLATE_WRAPPER_CLASS = """\
cdef class {class_name}:
  cdef {ctype} c_sim

  def __init__(self):
    pass

  cpdef void initialize(self):
    self.c_sim.{init}()

  cpdef void terminate(self):
    self.c_sim.{term}()

  def set_param(self, param):
    self.c_sim.{param} = self.{convert_param_p2c}(param)

  def get_param(self):
    return self.{convert_param_c2p}(self.c_sim.{param})

  cdef {output_type} _step(self, {input_type} rtU):
    self.c_sim.{input}(&rtU)
    self.c_sim.{step}()
    return self.c_sim.{output}()

  def step(self, input):
    rtu = self.{convert_in}(input)
    rty = self._step(rtu)
    return self.{convert_out}(rty)
"""

    TEMPLATE_ARRAY2NP = "np.asarray(<np.{dtype}[:{size}]> {name}).copy()"  # TODO: better way?
    TEMPLATE_CDEF_FIELD = "cdef {type} {name}"

    TEMPLATE_BUILDER = """\
from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy as np

extensions = [
  Extension(
    "{name}",
    [
      r"{f1}",
      r"{f2}",
      # r"{f3}",
    ],
    include_dirs=[np.get_include(), 'D:\\Program Files\\MATLAB\\R2018a\\simulink\\include']
  )
]

setup(ext_modules=cythonize(extensions))
"""

    TEMPLATE_GYM_GENERAL = """\
import gym
import {name}
class {model}Env(gym.Env):
  metadata = {{
    'render.modes': []
  }}
  reward_range = (-float('inf'), float('inf'))

  # NOTE: properly implement these two spaces, not that easy
  # action_space = ExtU_dtype
  # observation_space = ExtY_dtype

  initial_state = []

  def __init__(self):
    self._physics = None
    self.reset()

  def is_done(self, new_state) -> bool:
    '''
    Check if an episode is done.
    '''
    raise NotImplementedError

  def get_reward(self, new_state, action) -> float:
    '''
    Get reward of an action.
    '''
    raise NotImplementedError

  def step(self, action):
    state = self._step_physics(action)
    ret = np.array(state, dtype={input_type}_dtype), self.get_reward(state, action), self.is_done(state), {{}}
    self.state = state
    return ret

  def seed(self, seed=None):
    '''
    NOTE: Ramdomness is not properly handled yet !!!
    '''
    return [seed]

  def reset(self):
    '''Reset the environment.'''
    if self._physics is not None:
      self._physics.terminate()
    self._physics = {name}.{wrapper}()
    self._physics.initialize()
    self.state = {model}Env.initial_state
    return self.state

  def render(self, mode='human'):
    '''Render the environment.'''
    super({model}Env, self).render(mode=mode) # Just raise an exception

  def close(self):
    self._physics.terminate()

  def _step_physics(self, action):
    return self._physics.step(action)
"""

    TEMPLATE_GYM_COMPLIANT = """\
import gym
import {name}
class {model}Env(gym.Env):
  metadata = {{
    'render.modes': []
  }}
  reward_range = (-float('inf'), float('inf'))

  # NOTE: properly implement these two spaces, not that easy
  # action_space = ExtU_dtype
  # observation_space = ExtY_dtype

  def __init__(self):
    self._physics = None
    self.action_space = gym.spaces.Box()
    self.observation_space = gym.spaces.Box()
    self.reset()

  def is_done(self, new_state) -> bool:
    '''
    Check if an episode is done.
    '''
    raise NotImplementedError

  def get_reward(self, new_state, action) -> float:
    '''
    Get reward of an action.
    '''
    raise NotImplementedError

  def step(self, action):
    state = self._step_physics({{ 'Action': action }})
    self.state = state[0]
    ret = self.state, self.get_reward(state, action), self.is_done(state), {{}}
    return ret

  def seed(self, seed=None):
    '''
    NOTE: Ramdomness is not properly handled yet !!!
    '''
    return [seed]

  def reset(self):
    '''Reset the environment.'''
    if self._physics is not None:
      self._physics.terminate()
    self._physics = {name}.{wrapper}()

    # TODO: implement randomness here
    params = self._physics.get_param()
    # TODO: modify params as needed
    self._physics.set_param(params)

    self._physics.initialize()

    # TODO: properly provide initial state (according to params)
    # Or step once here to get a state as initial state
    initial_state = np.array([])

    self.state = initial_state
    return self.state

  def render(self, mode='human'):
    '''Render the environment.'''
    super({model}Env, self).render(mode=mode) # Just raise an exception

  def close(self):
    self._physics.terminate()

  def _step_physics(self, action):
    return self._physics.step(action)
"""

    def __init__(self, presets=None):
        if presets is None:
            presets = [WriterContext.DIRECTIVES, WriterContext.BANNER, WriterContext.CIMPORTS]
        self.indent_level = 0
        self.lines = []

        for preset in presets:
            for line in preset:
                self.write_line(line)
            self.write_line("")

    def indent_in(self):
        self.indent_level += 1

    def indent_out(self):
        self.indent_level -= 1
        assert self.indent_level >= 0

    @contextmanager
    def write_block(self, header: str, tail: str = None, append=False, blank_line=True):
        self.write_line(header, append=append)
        self.indent_in()
        try:
            yield
        finally:
            self.indent_out()
            if tail is not None:
                self.write_line(tail)
            if blank_line:
                self.write_line("")

    def write_line(self, line: str, append=False):
        if append:
            level, pre_line = self.lines[-1]
            self.lines[-1] = level, pre_line + line
        else:
            self.lines.append((self.indent_level, line))

    def to_string(self, indent_size=2):
        indent_unit = " " * indent_size
        return "\n".join([(level * indent_unit + line).rstrip() for level, line in self.lines])


class Transformer:
    def __init__(self, context: str, out: str):
        assert os.path.isdir(context), "Must be a directory"
        self.context = pathlib.Path(context)
        if out is None:
            self.out = self.context / "python_out"
        else:
            self.out = pathlib.Path(out)

        self.out.mkdir(exist_ok=True)
        self.type_registry = {}
        self.code_info = self.get_code_info()
        self.paths = self.generate_paths()

    def generate_files(self):
        defs = self.generate_def()
        self.paths["declaration"]["dest"].write_text(defs, encoding='utf-8')

        wrapper = self.generate_wrapper()
        self.paths["wrapper"]["dest"].write_text(wrapper, encoding='utf-8')

        builder = self.generate_builder()
        self.paths["builder"]["dest"].write_text(builder, encoding='utf-8')

        helper = self.generate_type_helper()
        write_text_safe(self.paths["helper"]["dest"], helper)  # To avoid overwrite user code

        shutil.copy(self.paths["header"]["src"], self.paths["header"]["dest"])
        shutil.copy(self.paths["source"]["src"], self.paths["source"]["dest"])
        # shutil.copy(self.paths["source_data"]["src"], self.paths["source_data"]["dest"])
        shutil.copy(self.paths["types"]["src"], self.paths["types"]["dest"])

        self.transform_source()

    def transform_source(self):
        MODEL_HEADER = self.paths["header"]["dest"]
        MODEL_SOURCE = self.paths["source"]["dest"]
        # MODEL_DATA = self.paths["source_data"]["dest"]

        with open(MODEL_HEADER, "r+") as model_header_file, open(MODEL_SOURCE, "r+") as model_source_file:
            # model_source = model_source_file.readlines()
            model_header = model_header_file.readlines()
            for i, line in enumerate(model_header):
                if line.endswith("private:\n"):
                    private_line = i
                    break
            else:
                raise AttributeError("Mal-formed header.")

            # for i, line in enumerate(model_source):
            #     if line.endswith(f'#include "{self.code_info["class"]["header"]}"\n'):
            #         include_line = i
            #         break
            # else:
            #     raise AttributeError("Mal-formed source.")

            # class_name = self.code_info['class']["name"]
            # variable_name = self.code_info['class']['mapping']['param']
            # typename = self.code_info['class']['fields'][self.code_info['class']['mapping']['param_inst']]["type"]
            # model_source.insert(include_line + 1, MODEL_SOURCE_INJECTIONS.format(variable_name))
            # model_header.insert(private_line, MODEL_HEADER_INJECTIONS.format(typename, variable_name, class_name))

            # MATLAB 2018a imcompatibility hack
            model_header[private_line] = "    public:\n"

            # model_source_file.seek(0)
            # model_source_file.writelines(model_source)
            model_header_file.seek(0)
            model_header_file.writelines(model_header)

    def get_code_info(self):
        def parse_method(method: dict):
            if not method["Type"]:
                assert isinstance(method["Type"], list)
                return_name = "void"
            else:
                return_name = self.register_type(method["Type"])

            if not method["Arguments"]:
                assert isinstance(method["Arguments"], list)
                arguement_name = ""
            else:
                arguement_name = self.register_type(method["Arguments"])

            return {
                "name": method["Name"],
                "arguments": arguement_name,
                "return": return_name,
            }

        def parse_field(field: dict):
            return {
                "name": field["Identifier"],
                "type": self.register_type(field["Type"])
            }

        CODE_INFO = os.path.join(self.context, "codeInfo.json")
        with open(CODE_INFO) as code_info_file:
            code_info = json.load(code_info_file)

            # TODO: data stores support?

            class_type = code_info["InitializeFunctions"]["Owner"]["Type"]

            # # ctor seems missing in MATLAB 2018a
            # ctor_prototype = code_info["ConstructorFunction"]["Prototype"]
            # assert not ctor_prototype["Arguments"]
            # assert not ctor_prototype["Return"]

            # BUT initialization seems consistent
            init_prototype = code_info["InitializeFunctions"]["Prototype"]
            ctor_name = class_type["Identifier"]

            # # Implementation seems missing in MATLAB 2018a
            # param = code_info["Parameters"][0]["Implementation"]["BaseRegion"]["ElementIdentifier"]
            param = "rtP"

            info = {
                "name": code_info["Name"],
                "sample_time": code_info["OutputFunctions"]["Timing"]["SamplePeriod"],
                "class": {
                    "name": ctor_name,
                    "header": init_prototype["HeaderFile"],
                    "source": init_prototype["SourceFile"],
                    "mapping": {
                        "ctor": ctor_name,
                        "init": code_info["InitializeFunctions"]["Prototype"]["Name"],
                        "step": code_info["OutputFunctions"]["Prototype"]["Name"],
                        "term": code_info["TerminateFunctions"]["Prototype"]["Name"],
                        "input": "setExternalInputs",  # TODO: more generic way?
                        "output": "getExternalOutputs",
                        # "param": code_info["Parameters"][0]["Implementation"]["BaseRegion"]["Identifier"],  # difference between Identifier and ElementIdentifier
                        "param": param,
                        "param_inst": param, # MATLAB 2018 different param impl   + "__actual",
                        # "param_type": class_type["Parameters"][0]["Implementation"]["BaseRegion"]["Type"]["Name"]
                    },
                    "methods": {method["Name"]: parse_method(method) for method in class_type["Methods"]},
                    "fields": {field["Identifier"]: parse_field(field) for field in class_type["Elements"] if not (field["Identifier"].endswith("_B") or field["Identifier"].endswith("_DW") or field["Identifier"].endswith("_X"))}
                }
            }

            self.mix_types(code_info["Types"])

            param_inst_name = info["class"]["mapping"]["param_inst"]
            param_inst = info["class"]["fields"].pop(info["class"]["mapping"]["param"])
            param_inst["name"] = param_inst_name
            info["class"]["fields"][param_inst_name] = param_inst

            return info

    def generate_def(self):
        writer = WriterContext()

        with writer.write_block(WriterContext.TEMPLATE_EXTERN.format(header=self.code_info["class"]["header"])):
            pending_scoped_defs = {}
            for type_name, type_def in self.type_registry.items():
                if type_def["mode"] == Types.SCALAR:
                    continue
                elif type_def["mode"] == Types.ARRAY:
                    continue  # seems not used by cython
                    # writer.write_line(WriterContext.TEMPLATE_CTYPEDEF_ARRAY.format(type=type_def["base"], size=type_def["size"], name=type_name))
                else:
                    scope = type_def["scope"]
                    if scope is None:
                        with writer.write_block(WriterContext.TEMPLATE_CTYPEDEF_STRUCT.format(name=type_name)):
                            for el in type_def["elements"]:
                                type_info = self.type_registry[el["type"]]
                                writer.write_line(type_info["repr"].format(name=el["name"]))
                    else:
                        if scope in pending_scoped_defs:
                            pending_scoped_defs[scope].append(type_def)
                        else:
                            pending_scoped_defs[scope] = [type_def]

            klass = self.code_info["class"]
            class_name = klass["name"]
            with writer.write_block(WriterContext.TEMPLATE_CDEF_CLASS.format(name=class_name)):
                if class_name in pending_scoped_defs:
                    for type_def in pending_scoped_defs[class_name]:
                        type_name = type_def["name"]
                        with writer.write_block(WriterContext.TEMPLATE_STRUCT.format(name=type_name)):
                            for el in type_def["elements"]:
                                type_info = self.type_registry[el["type"]]
                                writer.write_line(type_info["repr"].format(name=el["name"]))
                    del pending_scoped_defs[class_name]

                for method_name, method_def in klass["methods"].items():
                    if method_name == class_name:
                        writer.write_line(WriterContext.TEMPLATE_CTOR.format(name=class_name, args=""))
                    elif method_name == klass["mapping"]["input"]:
                        # TODO: not a elegant workaround
                        writer.write_line(WriterContext.TEMPLATE_METHOD.format(name=method_name,
                                                                               args=self.try_scope(method_def["arguments"]) + "*",
                                                                               ret=self.try_scope(method_def["return"])))
                    else:
                        writer.write_line(WriterContext.TEMPLATE_METHOD.format(name=method_name,
                                                                               args=self.try_scope(method_def["arguments"]),
                                                                               ret=self.try_scope(method_def["return"])))

                for field_name, field_def in klass["fields"].items():
                    writer.write_line(WriterContext.TEMPLATE_FIELD.format(name=field_name, type=field_def["type"]))

            assert not pending_scoped_defs
        return writer.to_string()

    def generate_wrapper(self):
        writer = WriterContext()

        convert_in = "convert_input"
        convert_in_param = "input_p"
        convert_out = "convert_output"
        convert_out_param = "output_c"
        convert_param_p2c = "convert_param_p2c"
        convert_param_p2c_param = "param_p"
        convert_param_c2p = "convert_param_c2p"
        convert_param_c2p_param = "param_c"

        klass = self.code_info["class"]
        class_name = klass["name"]
        wrapper_class_name = self.paths["wrapper"]["name"]
        mapping = klass["mapping"]

        input_type = self.try_scope(klass["methods"][mapping["input"]]["arguments"])
        output_type = self.try_scope(klass["methods"][mapping["output"]]["return"])
        param_type = self.try_scope(klass["fields"][mapping["param_inst"]]["type"])

        writer.write_line(WriterContext.TEMPLATE_CIMPORT.format(path=self.paths["declaration"]["name"], name=self.paths["declaration"]["name"]))
        with writer.write_block(WriterContext.TEMPLATE_WRAPPER_CLASS.format(
            class_name=wrapper_class_name,
            ctype=class_name,
            init=mapping["init"],
            term=mapping["term"],
            step=mapping["step"],
            input=mapping["input"],
            output=mapping["output"],
            input_type=input_type,
            output_type=output_type,
            convert_in=convert_in,
            convert_out=convert_out,
            convert_param_p2c=convert_param_p2c,
            convert_param_c2p=convert_param_c2p,
            param=mapping["param_inst"]
        )):
            writer.write_line("")

            # writer.write_line(WriterContext.TEMPLATE_WRAPPER_STATIC)
            with writer.write_block(WriterContext.TEMPLATE_WRAPPER_CDEF.format(name=convert_in, ret=input_type, args=convert_in_param)):
                self.generate_p2c_converter(writer, convert_in_param, klass["methods"][mapping["input"]]["arguments"])

            # writer.write_line(WriterContext.TEMPLATE_WRAPPER_STATIC)
            with writer.write_block(WriterContext.TEMPLATE_WRAPPER_CDEF.format(name=convert_out, ret="", args=output_type + " " + convert_out_param)):
                self.generate_c2p_converter_tuple(writer, convert_out_param, klass["methods"][mapping["output"]]["return"])

            # writer.write_line(WriterContext.TEMPLATE_WRAPPER_STATIC)
            with writer.write_block(WriterContext.TEMPLATE_WRAPPER_CDEF.format(name=convert_param_p2c, ret=param_type, args=convert_param_p2c_param)):
                self.generate_p2c_converter(writer, convert_param_p2c_param, klass["fields"][mapping["param_inst"]]["type"])

            # writer.write_line(WriterContext.TEMPLATE_WRAPPER_STATIC)
            with writer.write_block(WriterContext.TEMPLATE_WRAPPER_CDEF.format(name=convert_param_c2p, ret="", args=param_type + " " + convert_param_c2p_param)):
                self.generate_c2p_converter(writer, convert_param_c2p_param, klass["fields"][mapping["param_inst"]]["type"])
        return writer.to_string()

    def generate_builder(self):
        writer = WriterContext(presets=[WriterContext.BANNER])
        writer.write_line(WriterContext.TEMPLATE_BUILDER.format(name=self.code_info["name"],
                                                                f1=self.paths["wrapper"]["filename"],
                                                                f2=self.paths["source"]["filename"],
                                                                f3=self.paths["source_data"]["filename"]))
        return writer.to_string()

    def generate_type_helper(self):
        defined_structs = set()

        def generate_dataclass(name, elements):
            defined_structs.add(name)
            writer.write_line("@dataclass")
            with writer.write_block(f"class {name}:"):
                for el in elements:
                    el_info = self.type_registry[el["type"]]

                    if el_info['mode'] == Types.SCALAR:
                        writer.write_line(f"{el['name']}: {PY_TYPE_MAPPING[el['type']]}")
                    elif el_info['mode'] == Types.ARRAY:
                        writer.write_line(f"{el['name']}: np.ndarray")
                    else:
                        # if el["type"] not in defined_structs:
                        generate_dataclass(el["type"], el_info["elements"])
                        writer.write_line(f"{el['name']}: {el['type']}")

        def generate_np_structure(elements):
            for el in elements:
                el_info = self.type_registry[el["type"]]

                if el_info['mode'] == Types.SCALAR:
                    writer.write_line(f"('{el['name']}', {PY_NP_TYPE_MAPPING[el['type']]}),")
                elif el_info['mode'] == Types.ARRAY:
                    writer.write_line(f"('{el['name']}', {PY_NP_TYPE_MAPPING[el_info['base']]}, ({el_info['size']},)),")
                else:
                    with writer.write_block(f"('{el['name']}', [", "]),"):
                        generate_np_structure(el_info["elements"])

        writer = WriterContext(presets=[WriterContext.BANNER])
        writer.write_line(f"{self.code_info['name']}_SAMPLE_TIME = {self.code_info['sample_time']}")

        writer.write_line("from dataclasses import dataclass")
        writer.write_line("import numpy as np")

        klass = self.code_info["class"]
        mapping = klass["mapping"]
        param_type = klass["fields"][mapping["param_inst"]]["type"]
        input_type = klass["methods"][mapping["input"]]["arguments"]
        output_type = klass["methods"][mapping["output"]]["return"]
        for type_to_gen in [input_type, output_type, param_type]:
            type_info = self.type_registry[type_to_gen]
            generate_dataclass(type_to_gen, type_info["elements"])

        for type_to_gen in [input_type, output_type]:  # param_type meaningless here
            type_info = self.type_registry[type_to_gen]
            with writer.write_block(f"{type_to_gen}_dtype = [", "]"):
                generate_np_structure(type_info['elements'])

        # generate gym env
        if self.rl_compliant():
            writer.write_line(WriterContext.TEMPLATE_GYM_COMPLIANT.format(
                name=self.code_info["name"],
                model=self.code_info['class']['name'],
                input_type=input_type,
                wrapper=self.paths["wrapper"]["name"],
            ))
        else:
            writer.write_line(WriterContext.TEMPLATE_GYM_GENERAL.format(
                name=self.code_info["name"],
                model=self.code_info['class']['name'],
                input_type=input_type,
                wrapper=self.paths["wrapper"]["name"],
            ))

        return writer.to_string()

    def register_type(self, type_info: dict):
        def parse_element(el):
            return {
                "name": el["Identifier"],
                "type": self.register_type(el["Type"])
            }

        def nonscalar(size):
            if not isinstance(size, list):
                # temporary restriction for vector
                assert size > 1

                return size

            assert any([e != 1 for e in size])

            # temporary restriction for vector
            non_ones = [e for e in size if e != 1]
            assert len(non_ones) == 1
            return non_ones[0]

        # readonly ?
        # other types ?
        # TODO: exhaustive key enumeration
        # TODO: handle nested types
        def unroll(type_info):
            type_name = type_info["Name"]
            if "Dimensions" in type_info:
                type_info["Dimensions"] = reduce(lambda x, y: x * y, arrayify(type_info["Dimensions"]), 1)
                if type_info["Dimensions"] == 1:
                    if type_name.startswith("matrix1x1x"):
                        type_name = type_name[10:]
                    if type_name.startswith("matrix1x"):
                        type_name = type_name[8:]
                    # assert type_info["Name"] == type_name
                    type_info = type_info["BaseType"]
                    return unroll(type_info)
                else:
                    return type_name, type_info
            else:
                return type_name, type_info

        type_name, type_info = unroll(type_info)
        # if type_name.startswith("matrix1x1x"):
        #     assert "Dimensions" in type_info and all([el == 1 for el in type_info["Dimensions"]])
        #     type_name = type_name[10:]
        #     type_info = type_info["BaseType"]
        #     assert type_info["Name"] == type_name
        # if "Dimensions" in type_info and type_info["Dimensions"] == 1:
        #     type_name = type_name[8:]
        #     type_info = type_info["BaseType"]
        #     assert type_info["Name"] == type_name

        if type_name in TYPE_MAPPING:
            type_name = TYPE_MAPPING[type_name]

        if type_name in self.type_registry:
            return self.type_registry[type_name]["name"]

        if "Elements" in type_info:
            # struct-like types
            # assert type_info["Name"] == type_info["Identifier"]
            self.type_registry[type_name] = {
                "name": type_name,
                "mode": Types.STRUCT,
                "scope": None,
                "elements": [parse_element(el) for el in arrayify(type_info["Elements"])],
                "repr": "{} {};".format(type_name, "{name}")
            }
        elif "Dimensions" in type_info:
            # array-like types
            array_type = {
                "name": type_name,
                "mode": Types.ARRAY,
                "scope": None,
                "base": self.register_type(type_info["BaseType"]),
                "size": nonscalar(type_info["Dimensions"])
            }
            array_type["repr"] = "{} {}[{}];".format(array_type['base'], "{name}", array_type['size'])
            self.type_registry[type_name] = array_type
        else:
            # double(real_T)
            self.type_registry[type_name] = {
                "name": type_name,
                "scope": None,
                "mode": Types.SCALAR,
                "repr": "{} {};".format(type_name, "{name}")
            }
        return type_name

    def mix_types(self, types):
        for type in types:
            if type["Name"].startswith("B_") or type["Name"].startswith("DW_") or type["Name"].startswith("X_"):
                continue
            id: str = type["Identifier"]
            if "::" not in id:
                continue

            parts = id.split("::")
            assert len(parts) == 2
            scope, name = parts
            assert name == type["Name"]
            type_info = self.type_registry[name]
            type_info["scope"] = scope

    def try_scope(self, type_name):
        if type_name == "void" or type_name == "":
            return type_name
        type_info = self.type_registry[type_name]
        scope = type_info["scope"]
        if scope is None:
            # Seems buggy in MATLAB 2018a
            # return type_name
            return self.code_info["class"]["name"] + "." + type_name
        else:
            return scope + "." + type_name

    def generate_c2p_converter(self, writer: WriterContext, name: str, type: str, with_return=True, paths=None, append=False):
        if paths is None:
            paths = []
        prefix = "return " if with_return else ""
        type_info = self.type_registry[type]
        new_path = paths + [name]
        if type_info["mode"] == Types.SCALAR:
            writer.write_line(prefix + ".".join(new_path), append=append)
        elif type_info["mode"] == Types.ARRAY:
            # only scalar base type is currently supported
            dtype = NP_TYPE_MAPPING[type_info["base"]]
            writer.write_line(prefix + WriterContext.TEMPLATE_ARRAY2NP.format(name=".".join(new_path), size=type_info["size"], dtype=dtype), append=append)
        else:
            with writer.write_block(("return " if with_return else "") + "{", "}", append=append, blank_line=False):
                for el in type_info["elements"]:
                    writer.write_line(f'"{el["name"]}": ')
                    self.generate_c2p_converter(writer, el["name"], el["type"], with_return=False, paths=new_path, append=True)
                    writer.write_line(",", append=True)

    def generate_c2p_converter_tuple(self, writer: WriterContext, name: str, type: str, with_return=True, paths=None, append=False):
        if paths is None:
            paths = []
        prefix = "return " if with_return else ""
        type_info = self.type_registry[type]
        new_path = paths + [name]
        if type_info["mode"] == Types.SCALAR:
            writer.write_line(prefix + ".".join(new_path), append=append)
        elif type_info["mode"] == Types.ARRAY:
            # only scalar base type is currently supported
            dtype = NP_TYPE_MAPPING[type_info["base"]]
            writer.write_line(prefix + WriterContext.TEMPLATE_ARRAY2NP.format(name=".".join(new_path), size=type_info["size"], dtype=dtype), append=append)
        else:
            with writer.write_block(("return " if with_return else "") + "(", ")", append=append, blank_line=False):
                for el in type_info["elements"]:
                    # writer.write_line('"{name}": '.format(name=el["name"]))
                    self.generate_c2p_converter_tuple(writer, el["name"], el["type"], with_return=False, paths=new_path, append=False)
                    writer.write_line(",", append=True)

    def generate_p2c_converter(self, writer: WriterContext, name: str, type: str):
        # intended for structs
        type_info = self.type_registry[type]
        c_name = name + "_c"
        writer.write_line(WriterContext.TEMPLATE_CDEF_FIELD.format(type=self.try_scope(type), name=c_name))

        base_template = c_name + ".{} = " + name + ".{}"
        pending = [(type_info["elements"], [])]
        counter = 0
        while pending:
            elements, paths = pending.pop(0)
            for el in elements:
                counter += 1
                el_info = self.type_registry[el["type"]]
                new_paths = paths + [el["name"]]
                if el_info["mode"] == Types.SCALAR:
                    c_path_str = ".".join(new_paths)
                    tmp = "']['".join(new_paths)
                    p_path_str = f"['{tmp}']"
                    writer.write_line(f"{c_name}.{c_path_str} = {name}{p_path_str}")
                elif el_info["mode"] == Types.ARRAY:
                    # only scalar base type is currently supported
                    c_path_str = ".".join(new_paths)
                    tmp = "']['".join(new_paths)
                    p_path_str = f"['{tmp}']"
                    tmp_name = f"__tmp_view_{counter}"
                    writer.write_line(f"cdef {el_info['base']}[:] {tmp_name} = {name}{p_path_str}")
                    writer.write_line(f"{c_name}.{c_path_str} = &{tmp_name}[0]")
                else:
                    pending.append((el_info["elements"], new_paths))
        writer.write_line(f"return {c_name}")

    def rl_compliant(self):
        klass = self.code_info["class"]
        mapping = klass["mapping"]
        input_type = self.type_registry[klass["methods"][mapping["input"]]["arguments"]]
        output_type = self.type_registry[klass["methods"][mapping["output"]]["return"]]
        
        input_compliant = len(input_type["elements"]) == 1 and input_type["elements"][0]["name"] == "Action"

        # TODO: Reward and isDone
        output_compliant = len(output_type["elements"]) == 1 and output_type["elements"][0]["name"] == "State"

        return input_compliant and output_compliant

    def generate_paths(self):
        return {
            "declaration": {
                "name": self.code_info['class']['name'],
                "filename": f"{self.code_info['class']['name']}.pxd",
                "dest": self.out / f"{self.code_info['class']['name']}.pxd"
            },
            "wrapper": {
                "name": f"{self.code_info['class']['name']}_wrapper",
                "filename": f"{self.code_info['class']['name']}_wrapper.pyx",
                "dest": self.out / f"{self.code_info['class']['name']}_wrapper.pyx"
            },
            "builder": {
                "filename": "build.py",
                "dest": self.out / "build.py"
            },
            "helper": {
                "filename": f"{self.code_info['name']}_helper.py",
                "dest": self.out / f"{self.code_info['name']}_helper.py"
            },
            "header": {
                "filename": self.code_info["class"]["header"],
                "src": self.context / self.code_info["class"]["header"],
                "dest": self.out / self.code_info["class"]["header"]
            },
            "source": {
                "filename": self.code_info["class"]["source"],
                "src": self.context / self.code_info["class"]["source"],
                "dest": self.out / self.code_info["class"]["source"]
            },
            "source_data": {
                "filename": self.code_info["class"]["source"][:-4] + "_data.cpp",
                "src": self.context / (self.code_info["class"]["source"][:-4] + "_data.cpp"),
                "dest": self.out / (self.code_info["class"]["source"][:-4] + "_data.cpp")
            },
            "types": {
                "filename": "rtwtypes.h",
                "src": self.context / "rtwtypes.h",
                "dest": self.out / "rtwtypes.h"
            }
        }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Transform simulink codegen output.')
    parser.add_argument('context', type=str, help="The folder containing ecoder generated files.")
    parser.add_argument('--out', type=str, help="The folder for binding outputs. Default to python_out folder relative to context folder.", default=None)
    args = parser.parse_args()

    transformer = Transformer(context=args.context, out=args.out)
    # transformer.generate_def()
    transformer.generate_files()
    # transformer.transform()
