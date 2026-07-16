from glob import glob
from os.path import join
from os import makedirs, remove
from textwrap import dedent
from typing import List, Union
from pathlib import Path
from firehose.backends import Backend
from firehose.backends.aspn.utils import (
    INDENT,
    format_and_write_to_file,
    format_docstring,
    ASPN_PREFIX_LOWER,
)

meson_build_template = """
aspn_lcm_c_inc = include_directories('include', is_system : true)

aspn_lcm_c_srcs = [{filenames}]


override_options_lcm = []
if lcm_dep.version().version_compare('<1.5.0')
    override_options_lcm = 'warning_level=0'
endif

aspn_lcm_c_lib = static_library('aspn-lcm',
                            sources: aspn_lcm_c_srcs,
                            include_directories: aspn_lcm_c_inc,
                            dependencies: lcm_dep,
                            override_options: override_options_lcm)
aspn_lcm_c_dep = declare_dependency(include_directories: aspn_lcm_c_inc,
                                    link_with: aspn_lcm_c_lib)
meson.override_dependency('{ASPN_PREFIX_LOWER}-lcm', aspn_lcm_c_dep)
"""


class Struct:
    def __init__(self, struct_name: str):
        self.constructor_param_buf: List[str] = []
        self.struct_docstr: str = "<Missing LCM Docstring>"
        self.struct_fields_buf: List[str] = []
        self.struct_name: str = struct_name
        self.struct_template = dedent(f"""
            // This code is generated via firehose.
            // DO NOT hand edit code.  Make any changes required using the firehose repo instead

            package {ASPN_PREFIX_LOWER}_lcm;

            {{struct_docstr}}
            struct {self.struct_name} {{{{

            {INDENT}// Non ASPN. Do not use. Extra field encoding the struct name to disambiguate LCM type fingerprint hashes.
            {INDENT}int8_t icd_{self.struct_name};

            {{struct_fields}}
            }}}}
        """)


class AspnYamlToLCM(Backend):
    current_struct: Struct | None = None
    structs: List[Struct] = []

    def _remove_existing_output_files(self):
        for file in glob(f"{self.output_folder}/*.h"):
            remove(file)

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = output_root_folder
        makedirs(self.output_folder, exist_ok=True)
        self._remove_existing_output_files()

    def begin_struct(self, struct_name):
        if self.current_struct is not None:
            self.structs += [self.current_struct]
        self.current_struct = Struct(struct_name)

    def _format_struct_fields_buffer(self, struct: Struct):
        output = ''
        for line in struct.struct_fields_buf:
            if line.startswith('//'):
                output += f'{line};\n'
            else:
                output += f'{line};\n\n'
        return output

    def generate(self):
        if self.current_struct is not None:
            self.structs += [self.current_struct]
        base_filenames = []
        for struct in self.structs:
            file_contents = struct.struct_template.format(
                struct_docstr=format_docstring(
                    struct.struct_docstr, style="//"
                ),
                struct_fields=self._format_struct_fields_buffer(struct),
            )

            base_filenames += [f"{ASPN_PREFIX_LOWER}_lcm_{struct.struct_name}"]
            output_filename = join(
                self.output_folder, f"{struct.struct_name}.lcm"
            )
            format_and_write_to_file(file_contents, output_filename)
        self._generate_meson_build(base_filenames)

    def _generate_meson_build(self, base_filenames):
        filenames = ''
        for filename in base_filenames:
            filenames += f'\n\t\'src/{filename}.c\','
        filenames += '\n'
        meson_build = meson_build_template.format(
            filenames=filenames, ASPN_PREFIX_LOWER=ASPN_PREFIX_LOWER
        )
        output_directory = join(self.output_folder, '..', 'lcm', 'c')
        Path(output_directory).mkdir(parents=True, exist_ok=True)
        meson_build_filename = join(output_directory, 'meson.build')
        with open(meson_build_filename, "w", encoding="utf-8") as f:
            f.write(meson_build)

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # # # # # # # # # # # # # # # Backend Methods # # # # # # # # # # # # # # #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    def process_func_ptr_field_with_self(
        self,
        field_name: str,
        params,
        return_t,
        doc_string: str,
        nullable: bool = False,
    ):
        raise NotImplementedError

    def process_data_pointer_field(
        self,
        field_name: str,
        type_name: str,
        data_len: Union[str, int],
        doc_string: str,
        deref="",
        nullable: bool = False,
    ):
        if self.current_struct is None:
            return
        docstr = format_docstring(doc_string, indent=INDENT, style='//')
        field_str = f"{type_name} {field_name}[{data_len}]"
        self.current_struct.struct_fields_buf.append(
            f"{docstr}\n{INDENT}{field_str}"
        )

    def process_matrix_field(
        self,
        field_name: str,
        type_name: str,
        x: str | int,
        y: str | int,
        doc_string: str,
        nullable: bool = False,
    ):
        if self.current_struct is None:
            return
        docstr = format_docstring(doc_string, indent=INDENT, style='//')
        field_str = f"{type_name} {field_name}[{x}][{y}]"
        self.current_struct.struct_fields_buf.append(
            f"{docstr}\n{INDENT}{field_str}"
        )

    def process_outer_managed_pointer_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        raise NotImplementedError

    def process_outer_managed_pointer_array_field(
        self,
        field_name: str,
        field_type_name: str,
        data_len: Union[str, int],
        doc_string: str,
        deref="",
        nullable: bool = False,
    ):
        raise NotImplementedError

    def process_string_field(
        self, field_name: str, doc_string: str, nullable: bool = False
    ):
        self.process_simple_field(
            field_name, "string", doc_string, nullable=nullable
        )

    def process_string_array_field(
        self, field_name: str, doc_string: str, nullable: bool = False
    ):
        raise NotImplementedError

    def process_simple_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        if self.current_struct is None:
            return
        docstr = format_docstring(doc_string, indent=INDENT, style='//')
        field_str = f"{field_type_name} {field_name}"
        self.current_struct.struct_fields_buf.append(
            f"{docstr}\n{INDENT}{field_str}"
        )

    def process_class_docstring(self, doc_string: str, nullable: bool = False):
        if self.current_struct is not None:
            self.current_struct.struct_docstr = doc_string
        pass

    def process_inheritance_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        raise NotImplementedError

    def process_enum(
        self,
        field_name: str,
        field_type_name: str,
        enum_values: List[str],
        doc_string: str,
        enum_values_doc_strs: List[str],
        nullable: bool = False,
    ):
        enum_tuples = []
        max_int = 0
        for i, enum_val in enumerate(enum_values):
            e_val = i
            enum_split = enum_val.split('=')
            if len(enum_split) == 2:
                try:
                    e_val = int(enum_split[1])
                    enum_val = enum_split[0].strip()
                except ValueError:
                    print(
                        "Something strange is going on with enum field",
                        "name: '{num_val}' in struct '{self.struct_name}'",
                    )
            max_int = max(max_int, e_val)
            enum_tuples.append(
                (f'{enum_val} = {e_val}', enum_values_doc_strs[i])
            )

        # We seemingly only need to do this for 1 file (type_satnav_signal_descriptor)
        # which is setting the value to 129 for some reason when there are only 68 other enums
        enum_type = 'int8_t' if max_int < (2**8 / 2) else 'int16_t'

        self.process_simple_field(
            field_name, enum_type, doc_string, nullable=nullable
        )

        for field in enum_tuples:
            self.process_simple_field(
                field[0], f'const {enum_type}', field[1], nullable=nullable
            )
