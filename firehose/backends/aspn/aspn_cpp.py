from os import makedirs, sep
from os.path import join
from shutil import rmtree
from textwrap import dedent
from typing import List, Union

from ..backend import Backend
from .aspn_yaml_to_cpp_header import (
    AspnYamlToEigenHeader,
    AspnYamlToStlHeader,
    AspnYamlToXtensorHeader,
    AspnYamlToXtensorPyHeader,
)
from .aspn_yaml_to_cpp_source import (
    AspnYamlToEigenSource,
    AspnYamlToStlSource,
    AspnYamlToXtensorPySource,
    AspnYamlToXtensorSource,
)
from .utils import (
    ASPN_PREFIX,
    format_and_write_to_file,
    is_length_field,
    snake_to_pascal,
)

ASPN_DIR = ASPN_PREFIX.lower()

EXTRA_BINDINGS = {
    'TypeTimestamp': """.def(py::self + py::self)
	    .def(py::self + double())
	    .def(double() + py::self)
	    .def(py::self - py::self)
	    .def(py::self - double())
	    .def(double() - py::self)
	    .def(py::self == py::self)
	    .def(py::self != py::self)
	    .def(py::self < py::self)
	    .def(py::self > py::self)
	    .def(py::self <= py::self)
	    .def(py::self >= py::self)
	    .def(py::self == double())
	    .def(py::self != double())
	    .def(py::self < double())
	    .def(py::self > double())
	    .def(py::self <= double())
	    .def(py::self >= double())
	    .def(py::self == int())
	    .def(py::self != int())
	    .def(py::self < int())
	    .def(py::self > int())
	    .def(py::self <= int())
	    .def(py::self >= int())
	    .def(double() == py::self)
	    .def(double() != py::self)
	    .def(double() < py::self)
	    .def(double() > py::self)
	    .def(double() <= py::self)
	    .def(double() >= py::self)
	    .def(int() == py::self)
	    .def(int() != py::self)
	    .def(int() < py::self)
	    .def(int() > py::self)
	    .def(int() <= py::self)
	    .def(int() >= py::self)
	    .def("__repr__", [](const TypeTimestamp &t) {
		    std::ostringstream ss;
		    ss << t;
		    return ss.str();
	    })
    """,
    'TypeSatnavTime': """.def(py::self + double())
	    .def(py::self - double())
	    .def(py::self - py::self)
	    .def(py::self == py::self)
	    .def(py::self != py::self)
	    .def(py::self > py::self)
	    .def(py::self >= py::self)
	    .def(py::self < py::self)
	    .def(py::self <= py::self)
        .def("__repr__", [](const TypeSatnavTime& t) {
            std::ostringstream ss;
            ss << t;
            return ss.str();
	    })
    """,
}


class AspnCppBackend(Backend):
    def __init__(self):
        self.source_generators = [
            AspnYamlToXtensorSource(),
            AspnYamlToXtensorPySource(),
            AspnYamlToEigenSource(),
            AspnYamlToStlSource(),
        ]
        self.header_generators = [
            AspnYamlToXtensorHeader(),
            AspnYamlToXtensorPyHeader(),
            AspnYamlToEigenHeader(),
            AspnYamlToStlHeader(),
        ]
        self.all_source_files = []
        self.includes = []
        self.type_get_time_cases = ''
        self.type_set_time_cases = ''
        self.type_convert_message_cpp_cases = ''
        self.type_copy_message_cases = ''
        self.bindings = []
        self.getters_setters = ''
        self.types = []
        self.all_types = []

    def _remove_existing_output_files(self):
        rmtree(self.output_folder, ignore_errors=True)

    def _generate_meson_build(self):
        print("Generating meson.build")
        meson_build = dedent("""
            # This code is generated via firehose.
            # DO NOT hand edit code. Make any changes required using the firehose repo instead.

            required = get_option('aspn-cpp').enabled()

            xtensor_dep = disabler()
            if not get_option('aspn-cpp-xtensor').disabled() or not get_option('aspn-cpp-xtensor-py').disabled()
                xtensor_dep = dependency('xtensor',
                    version: ['>=0.21.4', '<1.0.0'],
                    fallback: ['xtensor', 'xtensor_dep'],
                    include_type: 'system',
                    method: 'pkg-config',
                    required: get_option('aspn-cpp-xtensor').enabled(),
                    disabler: true)
            endif

            xtensor_python_dep = disabler()
            pybind11_dep = disabler()
            libpython3_dep = disabler()
            if not get_option('aspn-cpp-xtensor-py').disabled()
                xtensor_python_dep = dependency('xtensor-python',
                    version: ['>=0.24.1', '<1.0.0'],
                    required: false,
                    allow_fallback: true,
                    disabler: true)

                pybind11 = subproject('pybind11', required: false)
                if pybind11.found()
                    pybind11_dep = pybind11.get_variable('pybind11_dep')
                else
                    pybind11_dep = disabler()
                endif

                python = import('python').find_installation('python3')
                libpython3_dep = python.dependency(embed: true, required: false)
            endif

            eigen_dep = disabler()
            if not get_option('aspn-cpp-eigen').disabled()
                eigen_dep = dependency('eigen3',
                    version: ['>=3.3.5'],
                    include_type: 'system',
                    required: get_option('aspn-cpp-eigen').enabled(),
                    allow_fallback: true,
                    disabler: true)
            endif

            aspn_stl_deps = [aspn_c_dep]
            aspn_xtensor_deps = [aspn_c_dep, xtensor_dep]
            aspn_xtensor_py_deps = [xtensor_dep, xtensor_python_dep, pybind11_dep]
            aspn_eigen_deps = [aspn_c_dep, eigen_dep]
        """)
        matrix_specific_template = dedent("""
            aspn_{matrix}_sources = [
            {sources}
            ]

            aspn_{matrix}_dep = disabler()

            if not get_option('aspn-cpp-{matrix_dash}').disabled()

                aspn_{matrix}_include = include_directories('src')

                aspn_{matrix}_libs = both_libraries('aspn-{matrix_dash}',
                    sources: aspn_{matrix}_sources,
                    include_directories: aspn_{matrix}_include,
                    dependencies: aspn_{matrix}_deps,
                    soversion: meson.project_version(),
                    install: true)

                aspn_{matrix}_dep = declare_dependency(
                    link_with: aspn_{matrix}_libs.get_shared_lib(),
                    include_directories: aspn_{matrix}_include ,
                    dependencies: aspn_{matrix}_deps)

                foreach source : aspn_{matrix}_sources
                    header = source.replace('.cpp', '.hpp')
                    install_headers(header, install_dir: get_option('includedir') + '/aspn23/{matrix}')
                endforeach

                pkg = import('pkgconfig')
                pkg.generate(aspn_{matrix}_libs,
                    name: 'aspn23-{matrix}',
                    description: 'ASPN cpp with {matrix} matrices',
                    version: meson.project_version())

                meson.override_dependency('aspn23-{matrix}', aspn_{matrix}_dep)

            endif
        """)
        for generator in self.header_generators:
            all_source_files = [
                join('src/', ASPN_DIR, generator.directory, source_file)
                for source_file in self.all_source_files
            ]
            all_source_files += [
                join(
                    'src',
                    ASPN_DIR,
                    generator.directory,
                    f'aspn_{generator.namespace}.cpp',
                )
            ]
            all_source_files = [
                f'    \'{source_file}\',' for source_file in all_source_files
            ]
            if type(generator) is AspnYamlToXtensorPyHeader:
                sources = '\n'.join(all_source_files)
                meson_build += f'''
aspn_xtensor_py_sources = [
    {sources}
]

aspn_xtensor_py_dep = disabler()

if not get_option('aspn-cpp-xtensor-py').disabled()
    aspn_xtensor_py_include = include_directories('src')

    aspn_xtensor_py_static_lib = static_library('aspn_xtensor_py',
        sources: [aspn_xtensor_py_sources, 'src/aspn23/xtensor_py/xtensor_bindings.cpp'],
        include_directories: aspn_xtensor_py_include,
        override_options: ['b_coverage=false', 'b_sanitize=none'],
        dependencies: [aspn_xtensor_py_deps, aspn_c_no_asan_dep])

    aspn_xtensor_py_dep = declare_dependency(
        link_whole: aspn_xtensor_py_static_lib,
        include_directories: [aspn_xtensor_py_include, aspn_c_inc_dir],
        dependencies: aspn_xtensor_py_deps)

    meson.override_dependency('aspn23-xtensor-py', aspn_xtensor_py_dep)

    python = import('python').find_installation('python3')
    python_bindings_lib = python.extension_module('{ASPN_DIR}_xtensor',
        sources: ['src/aspn23/xtensor_py/xtensor_bindings_module.cpp'],
        include_directories: aspn_xtensor_py_include,
        dependencies: aspn_xtensor_py_deps,
        override_options: ['b_coverage=false', 'b_sanitize=none'],
        link_whole: aspn_xtensor_py_static_lib,
        install: true)

    # The location of the Python extension module will be the current build directory
    # This can be added to PYTHONPATH to be able to import the module
    aspn_xtensor_python_lib_location = meson.current_build_dir()

    ### Stubgen

    pybind11_stubgen = find_program('pybind11-stubgen')

    if (pybind11_stubgen.found())

        generate_stubs = meson.project_source_root() / 'util' / 'generate_stubs.py'

        env = environment()
        env.append('PYTHONPATH', aspn_xtensor_python_lib_location)

        custom_target('stubs',
                      input : python_bindings_lib,
                      output : ['aspn23_xtensor.pyi' ],
                      command : [pybind11_stubgen, '-o' + meson.current_build_dir(), 'aspn23_xtensor'],
                      env: env,
                      build_by_default : true,
                      install: true,
                      install_tag: 'python-runtime',
                      install_dir: python.get_install_dir())
        install_data('py.typed',
                     install_tag: 'python-runtime',
                     install_dir: python.get_install_dir() / 'aspn23_xtensor')
    endif
endif
'''
            else:
                meson_build += matrix_specific_template.format(
                    matrix=generator.namespace,
                    matrix_dash=generator.namespace.replace('_', '-'),
                    sources='\n'.join(all_source_files),
                    aspn_dir=ASPN_DIR,
                )
        meson_build_filename = self.output_folder.replace(
            f'/src/{ASPN_DIR}', '/meson.build'
        )
        with open(meson_build_filename, "w", encoding="utf-8") as f:
            f.write(meson_build)

    def _generate_bindings(self):
        bindings_template = """
        #include <pybind11/eval.h>
        #include <pybind11/native_enum.h>
        #include <pybind11/operators.h>
        #include <pybind11/pybind11.h> // Pybind11 import to define Python bindings
        #include <pybind11/stl.h>

        #include <xtensor-python/pyarray.hpp> // Numpy bindings
        #include <xtensor-python/pytensor.hpp>

        #include "aspn_xtensor.hpp"

        // Used to pass parameter types by grouping a comma-separated collection of arguments to be passed
        // in as a single macro argument. Can be passed to constructor macros or overloaded function macros
        #define PARAMS(...) __VA_ARGS__

        using namespace aspn_xtensor;
        namespace py = pybind11;

        void add_bindings(pybind11::module& m) {{
            m.doc() = "ASPN C++ Xtensor";

            {bindings}

            m.def("to_type_timestamp",
                py::overload_cast<double>(&aspn_xtensor::to_type_timestamp),
                py::arg("t") = 0.0);
            m.def("to_type_timestamp",
                py::overload_cast<int64_t, int64_t>(&aspn_xtensor::to_type_timestamp),
                py::arg("sec"),
                py::arg("nsec"));
            m.def("to_seconds",
                py::overload_cast<const TypeTimestamp &>(&aspn_xtensor::to_seconds),
                py::arg("time"));
        }}

        """

        types_enum = f'''
        py::native_enum<{ASPN_PREFIX}MessageType>(m, "AspnMessageType", "enum.Enum")
        .value("ASPN_UNDEFINED", AspnMessageType::ASPN_UNDEFINED)
        '''
        for type in self.all_types + [
            'ASPN_EXTENDED_BEGIN',
            'ASPN_EXTENDED_END',
        ]:
            types_enum += f'.value("{type}", {ASPN_PREFIX}MessageType::{type})'
        types_enum += '.finalize();'
        self.bindings += [types_enum]

        if self.getters_setters != '':
            inheritance = (
                ', TypeHeader'
                if self.class_name.startswith('Measurement')
                or self.class_name.startswith('Metadata')
                or self.class_name == 'Image'
                else ''
            )
            self.bindings.append(
                self.binding_template.format(
                    class_name=self.class_name,
                    types=','.join(self.types),
                    getters_setters=self.getters_setters,
                    inheritance=inheritance,
                    extra_bindings=EXTRA_BINDINGS.get(self.class_name, ''),
                )
            )

        bindings = bindings_template.format(bindings='\n'.join(self.bindings))
        bindings_filename = join(
            self.output_folder, 'xtensor_py', 'xtensor_bindings.cpp'
        )
        format_and_write_to_file(bindings, bindings_filename)

    def _generate_aspn_root_header(self):
        aspn_h_template = """
            // This code is generated via firehose.
            // DO NOT hand edit code. Make any changes required using the firehose repo instead.

            #pragma once

            #include <functional>
            #include <memory>
            
            {xtensor_include}

            #include <{aspn_lower}/aspn.h>
            {includes}

            namespace aspn_{matrix} = {aspn_lower}_{matrix};

            namespace {aspn_lower}_{matrix} {{

            // An alias for cases where the object has been up-casted and should be
            // down-casted before using it.
            using AspnBase = TypeHeader;

            bool is_core_message(std::shared_ptr<{aspn_lower}_{matrix}::AspnBase> base);

            TypeTimestamp get_time(std::shared_ptr<{aspn_lower}_{matrix}::AspnBase> parent);
            void set_time(std::shared_ptr<{aspn_lower}_{matrix}::AspnBase> parent, TypeTimestamp time);

            TypeTimestamp convert_time(const AspnTypeTimestamp& time);
            AspnTypeTimestamp convert_time(const TypeTimestamp& time);

            /**
            * Downcasts \p parent to the type specified by parent->message_type,
            * passes it to the appropriate ASPN-C++ class' constructor, then returns the
            * up-casted result. This process renders \p parent unusable by stealing the
            * underlying data.
            *
            * If \p take_ownership is set to true, then the C++ object will assume
            * ownership of the C object. This means that the C++ object will destroy
            * the C object at the end of the C++ object's life. If \p take_ownership is
            * set to false then the caller is responsible for cleaning up the C object.
            *
            * If \p custom_deleter is set, then the returned shared_ptr will use the
            * custom deleter when cleaning up memory for the return type.
            *
            * Warning: this function should only be called with message type that has
            * been up-casted to a {aspn_prefix}TypeHeader (AspnBase), never an actual
            * {aspn_prefix}TypeHeader.
            */
            std::shared_ptr<{aspn_lower}_{matrix}::AspnBase> convert_message({aspn_prefix}TypeHeader* parent, bool take_ownership = true, std::function<void({aspn_lower}_{matrix}::AspnBase*)> custom_deleter = std::default_delete<{aspn_lower}_{matrix}::AspnBase>());

            /**
            * Downcasts \p parent to the type specified by parent->get_message_type(),
            * copies the data, then returns the up-casted result.
            *
            * Warning: this function should only be called with message type that has
            * been up-casted to a TypeHeader ({aspn_lower}_{matrix}::AspnBase), never an actual TypeHeader.
            */
            std::shared_ptr<{aspn_lower}_{matrix}::AspnBase> copy_message(std::shared_ptr<{aspn_lower}_{matrix}::AspnBase> parent);

            }}


            {xtensor_fixed_shape_equals_operator}
        """

        aspn_c_template = """
            // This code is generated via firehose.
            // DO NOT hand edit code. Make any changes required using the firehose repo instead.

            #include <{aspn_lower}/{matrix}/aspn_{matrix}.hpp>

            #include <memory>
            #include <stdexcept>

            namespace {aspn_lower}_{matrix} {{

            bool is_core_message(std::shared_ptr<{aspn_lower}_{matrix}::AspnBase> base) {{
                if (base == nullptr)
                    throw std::invalid_argument("is_core_message received a nullptr");
                return base->get_message_type() <= ASPN_LAST_MESSAGE;
            }}

            TypeTimestamp get_time(std::shared_ptr<{aspn_lower}_{matrix}::AspnBase> parent) {{
	        if (parent == nullptr) {{
                throw std::invalid_argument("get_time received a nullptr");
            }}
            switch(parent->get_message_type()) {{
            {type_get_time_cases}
                default: {{
                    throw std::invalid_argument("get_time called on a non-ASPN-core message");
                }}
                }}
            }}


            void set_time(std::shared_ptr<{aspn_lower}_{matrix}::AspnBase> parent, TypeTimestamp time) {{
	        if (parent == nullptr)
                throw std::invalid_argument("set_time received a nullptr");
            switch(parent->get_message_type()) {{
            {type_set_time_cases}
                default: {{
                    throw std::invalid_argument("set_time called on a non-ASPN-core message");
                }}
                }}
            }}

            TypeTimestamp convert_time(const AspnTypeTimestamp& time) {{
                return time.elapsed_nsec;
            }}

            AspnTypeTimestamp convert_time(const TypeTimestamp& time) {{
                AspnTypeTimestamp out = {{time.get_elapsed_nsec()}};
                return out;
            }}

            std::shared_ptr<{aspn_lower}_{matrix}::AspnBase> convert_message({aspn_prefix}TypeHeader* parent, bool take_ownership, std::function<void({aspn_lower}_{matrix}::AspnBase*)> custom_deleter) {{
	        if (parent == nullptr)
                throw std::invalid_argument("convert_message received a nullptr");
            switch(parent->message_type) {{
            {type_convert_message_cpp_cases}
                default: {{
                    throw std::invalid_argument("convert_message called on a non-ASPN-core message");
                }}
                }}
            }}

            std::shared_ptr<{aspn_lower}_{matrix}::AspnBase> copy_message(std::shared_ptr<{aspn_lower}_{matrix}::AspnBase> parent) {{
	        if (parent == nullptr) return nullptr;
            switch(parent->get_message_type()) {{
            {type_copy_message_cases}
                default: {{
                    return nullptr;
                }}
                }}
            }}

            }} // namespace {aspn_lower}_{matrix}

        """

        xtensor_include = """
            // xtensor
            #include <xtensor/containers/xfixed.hpp>
        """

        xtensor_fixed_shape_equals_operator = """
            namespace xt {

            /**
            * Operator for comparing `xt::fixed_shape` type.
            *
            * This function is needed to allow for fine-grain tensor typing in ASPN
            * messages.  For some reason, xtensor doesn't have a built in `==` operator
            * for `xt::fixed_shape` type, causing the debug build of NavTK to fail
            * because of xtensor shape asserts.  This is a known issue in xtensor
            * (see https://github.com/xtensor-stack/xtensor/issues/2376).
            */
            template <size_t... I1, size_t... I2>
            constexpr bool operator==(const fixed_shape<I1...>&, const fixed_shape<I2...>&) {
                if constexpr (sizeof...(I1) != sizeof...(I2)) {
                    return false;
                } else {
                    constexpr size_t shape1[] = {I1...};
                    constexpr size_t shape2[] = {I2...};

                    for (size_t i = 0; i < sizeof...(I1); i++) {
                        if (shape1[i] != shape2[i]) {
                            return false;
                        }
                    }
                    return true;
                }
            }
            }  // namespace xt
        """

        for generator in self.header_generators:
            print(f"Generating aspn_{generator.namespace}.hpp")
            output_filepath = join(
                self.output_folder,
                generator.directory,
                f"aspn_{generator.namespace}.hpp",
            )

            includes = [
                include.replace(
                    '<', '<' + ASPN_DIR + sep + generator.directory + sep
                )
                for include in self.includes
            ]
            aspn_h = aspn_h_template.format(
                matrix=generator.namespace,
                aspn_lower=ASPN_PREFIX.lower(),
                aspn_prefix=ASPN_PREFIX,
                includes='\n'.join(includes),
                xtensor_fixed_shape_equals_operator=(
                    xtensor_fixed_shape_equals_operator
                    if generator.namespace == 'xtensor'
                    else ''
                ),
                xtensor_include=(
                    xtensor_include if generator.namespace == 'xtensor' else ''
                ),
            )
            format_and_write_to_file(aspn_h, output_filepath)

            print(f"Generating aspn_{generator.namespace}.cpp")
            output_filepath = join(
                self.output_folder,
                generator.directory,
                f"aspn_{generator.namespace}.cpp",
            )
            aspn_c = aspn_c_template.format(
                matrix=generator.namespace,
                aspn_lower=ASPN_PREFIX.lower(),
                aspn_prefix=ASPN_PREFIX,
                type_get_time_cases=self.type_get_time_cases,
                type_set_time_cases=self.type_set_time_cases,
                type_convert_message_cpp_cases=self.type_convert_message_cpp_cases,
                type_copy_message_cases=self.type_copy_message_cases,
            )
            format_and_write_to_file(aspn_c, output_filepath)

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = join(output_root_folder, 'src', ASPN_DIR)
        self._remove_existing_output_files()

        for generator in self.source_generators:
            output_folder = join(self.output_folder, generator.directory)
            makedirs(output_folder, exist_ok=True)
            generator.set_output_root_folder(output_folder)

        for generator in self.header_generators:
            output_folder = join(self.output_folder, generator.directory)
            makedirs(output_folder, exist_ok=True)
            generator.set_output_root_folder(output_folder)

    def begin_struct(self, struct_name: str):
        self.binding_template = '''
        py::class_<{class_name}{inheritance}, py::smart_holder>(m, "{class_name}")
        .def(py::init<PARAMS({types})>())
        {getters_setters}{extra_bindings};
        '''

        if self.getters_setters != '':
            inheritance = (
                ', TypeHeader'
                if self.class_name.startswith('Measurement')
                or self.class_name.startswith('Metadata')
                or self.class_name == 'Image'
                else ''
            )
            self.bindings.append(
                self.binding_template.format(
                    class_name=self.class_name,
                    types=','.join(self.types),
                    getters_setters=self.getters_setters,
                    inheritance=inheritance,
                    extra_bindings=EXTRA_BINDINGS.get(self.class_name, ''),
                )
            )
            self.types = []
            self.getters_setters = ''

        self.struct_name = struct_name
        self.class_name = snake_to_pascal(struct_name)

        print(f"Generating ASPN-C++ for {self.struct_name}")

        for generator in self.source_generators:
            generator.begin_struct(self.struct_name)
        for generator in self.header_generators:
            generator.begin_struct(self.struct_name)

        if (
            self.struct_name.startswith('measurement')
            or self.struct_name.startswith('metadata')
            or self.class_name == 'Image'
        ):
            current_type = 'ASPN_' + struct_name.upper()

            self.type_get_time_cases += f"""
            case {current_type}: {{
                auto child = std::dynamic_pointer_cast<{self.class_name}>(parent);
                return child->get_time_of_validity();
            }}
            """

            self.type_set_time_cases += f"""
            case {current_type}: {{
                auto child = std::dynamic_pointer_cast<{self.class_name}>(parent);
                child->set_time_of_validity(time);
                return;
            }}
            """

            basename = f'{ASPN_PREFIX.lower()}_{self.struct_name.lower()}'

            self.type_convert_message_cpp_cases += f"""
            case {current_type}: {{
                auto child = ({ASPN_PREFIX}{self.class_name}*)parent;
                return std::shared_ptr<{self.class_name}>(new {self.class_name}(child, take_ownership), custom_deleter);
            }}
            """

            self.type_copy_message_cases += f"""
            case {current_type}: {{
                auto child = *std::dynamic_pointer_cast<{self.class_name}>(parent);
                std::shared_ptr<TypeHeader> copy = std::make_shared<{self.class_name}>({self.class_name}(child));
                return copy;
            }}
            """

            self.all_types += [current_type]

        self.all_source_files += [f'{self.class_name}.cpp']
        self.includes += [f'#include "{self.class_name}.hpp"']

    def process_func_ptr_field_with_self(
        self,
        field_name: str,
        params,
        return_t,
        doc_string: str,
        nullable: bool = False,
    ):
        for generator in self.source_generators:
            generator.process_func_ptr_field_with_self(
                field_name, params, return_t, doc_string, nullable
            )
        for generator in self.source_generators:
            generator.process_func_ptr_field_with_self(
                field_name, params, return_t, doc_string, nullable
            )
        self.getters_setters += f'''\
            .def("get_{field_name}", &{self.class_name}::get_{field_name})
            .def("set_{field_name}", &{self.class_name}::set_{field_name})
                             '''

    def process_data_pointer_field(
        self,
        field_name: str,
        type_name: str,
        data_len: Union[str, int],
        doc_string: str,
        deref="",
        nullable: bool = False,
    ):
        for generator in self.source_generators:
            generator.process_data_pointer_field(
                field_name, type_name, data_len, doc_string, deref, nullable
            )
        for generator in self.header_generators:
            generator.process_data_pointer_field(
                field_name, type_name, data_len, doc_string, deref, nullable
            )
        self.getters_setters += f'''\
            .def("get_{field_name}", &{self.class_name}::get_{field_name})
            .def("set_{field_name}", &{self.class_name}::set_{field_name})\
                             '''
        if ASPN_PREFIX in type_name:
            self.types += [
                f'std::vector<{type_name.removeprefix(ASPN_PREFIX)}>'
            ]
        else:
            self.types += [f'xt::pyarray<{type_name}>']

    def process_matrix_field(
        self,
        field_name: str,
        type_name: str,
        x: int,
        y: int,
        doc_string: str,
        nullable: bool = False,
    ):
        for generator in self.source_generators:
            generator.process_matrix_field(
                field_name, type_name, x, y, doc_string, nullable
            )
        for generator in self.header_generators:
            generator.process_matrix_field(
                field_name, type_name, x, y, doc_string, nullable
            )
        self.getters_setters += f'''\
            .def("get_{field_name}", &{self.class_name}::get_{field_name})
            .def("set_{field_name}", &{self.class_name}::set_{field_name})
                             '''
        self.types += [f'xt::pyarray<{type_name}>']

    def process_outer_managed_pointer_field(
        self, field_name: str, field_type_name: str, doc_string: str
    ):
        for generator in self.source_generators:
            generator.process_outer_managed_pointer_field(
                field_name, field_type_name, doc_string
            )
        for generator in self.header_generators:
            generator.process_outer_managed_pointer_field(
                field_name, field_type_name, doc_string
            )
        self.getters_setters += f'''\
            .def("get_{field_name}", &{self.class_name}::get_{field_name})
            .def("set_{field_name}", &{self.class_name}::set_{field_name})
                             '''

    def process_outer_managed_pointer_array_field(
        self,
        field_name: str,
        field_type_name: str,
        data_len: Union[str, int],
        doc_string: str,
        deref="",
        nullable: bool = False,
    ):
        for generator in self.source_generators:
            generator.process_outer_managed_pointer_array_field(
                field_name,
                field_type_name,
                data_len,
                doc_string,
                deref,
                nullable,
            )
        for generator in self.header_generators:
            generator.process_outer_managed_pointer_array_field(
                field_name,
                field_type_name,
                data_len,
                doc_string,
                deref,
                nullable,
            )
        self.getters_setters += f'''\
            .def("get_{field_name}", &{self.class_name}::get_{field_name})
            .def("set_{field_name}", &{self.class_name}::set_{field_name})
                             '''

    def process_string_field(
        self, field_name: str, doc_string: str, nullable: bool = False
    ):
        for generator in self.source_generators:
            generator.process_string_field(field_name, doc_string, nullable)
        for generator in self.header_generators:
            generator.process_string_field(field_name, doc_string, nullable)
        self.getters_setters += f'''\
            .def("get_{field_name}", &{self.class_name}::get_{field_name})
            .def("set_{field_name}", &{self.class_name}::set_{field_name})
                             '''
        self.types += ['char*']

    def process_string_array_field(
        self, field_name: str, doc_string: str, nullable: bool = False
    ):
        for generator in self.source_generators:
            generator.process_string_array_field(
                field_name, doc_string, nullable
            )
        for generator in self.header_generators:
            generator.process_string_array_field(
                field_name, doc_string, nullable
            )
        self.getters_setters += f'''\
            .def("get_{field_name}", &{self.class_name}::get_{field_name})
            .def("set_{field_name}", &{self.class_name}::set_{field_name})
                             '''

    def process_simple_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        for generator in self.source_generators:
            generator.process_simple_field(
                field_name, field_type_name, doc_string, nullable
            )
        for generator in self.header_generators:
            generator.process_simple_field(
                field_name, field_type_name, doc_string, nullable
            )
        if not is_length_field(field_name):
            self.getters_setters += f'''\
            .def("get_{field_name}", &{self.class_name}::get_{field_name})
            .def("set_{field_name}", &{self.class_name}::set_{field_name})
                             '''
            if f'{ASPN_PREFIX}Type' in field_type_name:
                field_type_name = field_type_name.removeprefix(ASPN_PREFIX)
            self.types += [field_type_name]

    def process_class_docstring(self, doc_string: str, nullable: bool = False):
        for generator in self.source_generators:
            generator.process_class_docstring(doc_string, nullable)
        for generator in self.header_generators:
            generator.process_class_docstring(doc_string, nullable)

    def process_inheritance_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        for generator in self.source_generators:
            generator.process_inheritance_field(
                field_name, field_type_name, doc_string, nullable
            )
        for generator in self.header_generators:
            generator.process_inheritance_field(
                field_name, field_type_name, doc_string, nullable
            )
        self.getters_setters += f'''\
            .def("get_{field_name}", &{self.class_name}::get_{field_name})
            .def("set_{field_name}", &{self.class_name}::set_{field_name})
                             '''

    def process_enum(
        self,
        field_name: str,
        field_type_name: str,
        enum_values: List[str],
        doc_string: str,
        enum_values_doc_strs: List[str],
    ):
        for generator in self.source_generators:
            generator.process_enum(
                field_name,
                field_type_name,
                enum_values,
                doc_string,
                enum_values_doc_strs,
            )
        for generator in self.header_generators:
            generator.process_enum(
                field_name,
                field_type_name,
                enum_values,
                doc_string,
                enum_values_doc_strs,
            )
        self.getters_setters += f'''\
            .def("get_{field_name}", &{self.class_name}::get_{field_name})
            .def("set_{field_name}", &{self.class_name}::set_{field_name})
                             '''
        self.types += [field_type_name]

        if enum_values != []:
            unversioned_type_name = field_type_name.replace(
                ASPN_PREFIX, 'Aspn'
            )
            enum = f'py::native_enum<{field_type_name}>(m, "{unversioned_type_name}", "enum.Enum")'
            for enum_value in enum_values:
                enum_value = enum_value.split('=')[0]
                enum_value = enum_value.replace(ASPN_PREFIX.upper(), 'ASPN')
                enum += (
                    f'.value("{enum_value}", {field_type_name}::{enum_value})'
                )
            enum += '.finalize();'
            self.bindings += [enum]

    def generate(self):
        for generator in self.source_generators:
            generator.generate()
        for generator in self.header_generators:
            generator.generate()

        self._generate_aspn_root_header()
        self._generate_meson_build()
        self._generate_bindings()
