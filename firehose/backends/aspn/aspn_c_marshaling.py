from glob import glob
from os import makedirs, remove
from os.path import join
from textwrap import dedent
from typing import List, Union
from ..backend import Backend
from .aspn_yaml_to_marshal_lcm_to_c_source import AspnYamlToMarshalLCMToCSource
from .aspn_yaml_to_marshal_c_to_lcm_source import AspnYamlToMarshalCToLCMSource
from .aspn_yaml_to_test_marshal_aspn23 import AspnYamlToTestMarshalAspn23
from .utils import (
    ASPN_PREFIX,
    ASPN_PREFIX_UNVERSIONED,
    ASPN_PREFIX_LOWER,
    ASPN_PREFIX_UNVERSIONED_UPPER,
    ASPN_PREFIX_UNVERSIONED_LOWER,
    format_and_write_to_file,
    snake_to_pascal,
)

MARSHAL_LCM_C_DIR = "marshal_lcm_c"


class Struct:
    def __init__(self, snake_case_struct_name: str):
        self.struct_docstr: str = "<Missing C Docstring>"
        self.struct_name: str = (
            f"{ASPN_PREFIX_UNVERSIONED}{snake_to_pascal(snake_case_struct_name)}"
        )
        self.struct_name_versioned: str = (
            f"{ASPN_PREFIX}{snake_to_pascal(snake_case_struct_name)}"
        )
        self.struct_name_lcm: str = (
            f"{ASPN_PREFIX_LOWER}_lcm_{snake_case_struct_name}"
        )
        self.struct_enum: str = (
            f"{ASPN_PREFIX_UNVERSIONED_UPPER}_{snake_case_struct_name}".upper()
        )
        self.fn_basename: str = (
            f"{ASPN_PREFIX_UNVERSIONED_LOWER}_{snake_case_struct_name}".lower()
        )
        self.include_template = dedent(
            f"""#include <{self.struct_name_lcm}.h>\n"""
        )
        self.from_function_template = dedent(
            f"""
            {self.struct_name}* marshal_{self.struct_name_lcm}({self.struct_name_lcm}* lcm_msg);\n"""
        )
        self.to_function_template = dedent(
            f"""
            void marshal_{self.struct_name_versioned}({self.struct_name_lcm}* lcm_msg, const {self.struct_name}* aspn);\n"""
        )
        self.header_template = dedent("""/*
             * This code is generated via firehose.
             * DO NOT hand edit code.  Make any changes required using the firehose repo instead
             */

            #pragma once

            {includes}

            #include <aspn.h>

            #ifdef __cplusplus
            extern "C" {{
            #endif

            {functions}

            #ifdef __cplusplus
            }}  // extern "C"
            #endif
        """)


class AspnCMarshalingBackend(Backend):
    def __init__(self):
        self.marshal_lcm_to_c_source_generator = (
            AspnYamlToMarshalLCMToCSource()
        )
        self.marshal_c_to_lcm_source_generator = (
            AspnYamlToMarshalCToLCMSource()
        )
        self.test_marshal_aspn23_c_generator = AspnYamlToTestMarshalAspn23()
        self.header_current_struct: Struct = None
        self.header_structs: List[Struct] = []

    def _remove_existing_output_files(self):
        for file in glob(f"{self.output_folder}/*.h"):
            remove(file)

        for file in glob(f"{self.output_folder}/*.c"):
            remove(file)

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = join(output_root_folder, MARSHAL_LCM_C_DIR)
        makedirs(self.output_folder, exist_ok=True)
        self._remove_existing_output_files()

        self.marshal_lcm_to_c_source_generator.set_output_root_folder(
            self.output_folder
        )
        self.marshal_c_to_lcm_source_generator.set_output_root_folder(
            self.output_folder
        )
        self.test_marshal_aspn23_c_generator.set_output_root_folder(
            self.output_folder
        )

    def begin_struct(self, struct_name: str):
        self.struct_name = struct_name

        print(f"Generating ASPN-C-Marshaling for {self.struct_name}")

        self.marshal_lcm_to_c_source_generator.begin_struct(self.struct_name)
        self.marshal_c_to_lcm_source_generator.begin_struct(self.struct_name)
        self.test_marshal_aspn23_c_generator.begin_struct(self.struct_name)

        if self.header_current_struct is not None:
            self.header_structs += [self.header_current_struct]
        self.header_current_struct = Struct(struct_name)

    def _generate_from_header(self):
        self.header_structs += [self.header_current_struct]
        includes_buf = ""
        functions_buf = ""
        for struct in self.header_structs:
            if struct.struct_name not in [
                f"{ASPN_PREFIX_UNVERSIONED}TypeIntegrity",
                f"{ASPN_PREFIX_UNVERSIONED}TypeHeader",
                f"{ASPN_PREFIX_UNVERSIONED}TypeMetadataheader",
            ]:
                includes_buf += struct.include_template.format()
                functions_buf += struct.from_function_template.format()
        c_file_contents = self.header_current_struct.header_template.format(
            includes=includes_buf, functions=functions_buf
        )
        c_output_filename = join(self.output_folder, "marshal_from_lcm.h")
        format_and_write_to_file(c_file_contents, c_output_filename)

    def _generate_to_header(self):
        self.header_structs += [self.header_current_struct]
        includes_buf = ""
        functions_buf = ""
        for struct in self.header_structs:
            if struct.struct_name not in [
                f"{ASPN_PREFIX_UNVERSIONED}TypeIntegrity",
                f"{ASPN_PREFIX_UNVERSIONED}TypeHeader",
                f"{ASPN_PREFIX_UNVERSIONED}TypeMetadataheader",
            ]:
                includes_buf += struct.include_template.format()
                functions_buf += struct.to_function_template.format()
        c_file_contents = self.header_current_struct.header_template.format(
            includes=includes_buf, functions=functions_buf
        )
        c_output_filename = join(self.output_folder, "marshal_to_lcm.h")
        format_and_write_to_file(c_file_contents, c_output_filename)

    def process_func_ptr_field_with_self(
        self,
        field_name: str,
        params,
        return_t,
        doc_string: str,
        nullable: bool = False,
    ):
        self.marshal_lcm_to_c_source_generator.process_func_ptr_field_with_self(
            field_name, params, return_t, doc_string, nullable
        )
        self.marshal_c_to_lcm_source_generator.process_func_ptr_field_with_self(
            field_name, params, return_t, doc_string, nullable
        )
        self.test_marshal_aspn23_c_generator.process_func_ptr_field_with_self(
            field_name, params, return_t, doc_string, nullable
        )

    def process_data_pointer_field(
        self,
        field_name: str,
        type_name: str,
        data_len: Union[str, int],
        doc_string: str,
        deref="",
        nullable: bool = False,
    ):
        self.marshal_lcm_to_c_source_generator.process_data_pointer_field(
            field_name, type_name, data_len, doc_string, deref, nullable
        )
        self.marshal_c_to_lcm_source_generator.process_data_pointer_field(
            field_name, type_name, data_len, doc_string, deref, nullable
        )
        self.test_marshal_aspn23_c_generator.process_data_pointer_field(
            field_name, type_name, data_len, doc_string, deref, nullable
        )

    def process_matrix_field(
        self,
        field_name: str,
        type_name: str,
        x: int | str,
        y: int | str,
        doc_string: str,
        nullable: bool = False,
    ):
        self.marshal_lcm_to_c_source_generator.process_matrix_field(
            field_name, type_name, x, y, doc_string, nullable
        )
        self.marshal_c_to_lcm_source_generator.process_matrix_field(
            field_name, type_name, x, y, doc_string, nullable
        )
        self.test_marshal_aspn23_c_generator.process_matrix_field(
            field_name, type_name, x, y, doc_string, nullable
        )

    def process_outer_managed_pointer_field(
        self, field_name: str, field_type_name: str, doc_string: str
    ):
        self.marshal_lcm_to_c_source_generator.process_outer_managed_pointer_field(
            field_name, field_type_name, doc_string
        )
        self.marshal_c_to_lcm_source_generator.process_outer_managed_pointer_field(
            field_name, field_type_name, doc_string
        )
        self.test_marshal_aspn23_c_generator.process_outer_managed_pointer_field(
            field_name, field_type_name, doc_string
        )

    def process_outer_managed_pointer_array_field(
        self,
        field_name: str,
        field_type_name: str,
        data_len: Union[str, int],
        doc_string: str,
        deref="",
        nullable: bool = False,
    ):
        self.marshal_lcm_to_c_source_generator.process_outer_managed_pointer_array_field(
            field_name, field_type_name, data_len, doc_string, deref, nullable
        )
        self.marshal_c_to_lcm_source_generator.process_outer_managed_pointer_array_field(
            field_name, field_type_name, data_len, doc_string, deref, nullable
        )
        self.test_marshal_aspn23_c_generator.process_outer_managed_pointer_array_field(
            field_name, field_type_name, data_len, doc_string, deref, nullable
        )

    def process_string_field(
        self, field_name: str, doc_string: str, nullable: bool = False
    ):
        self.marshal_lcm_to_c_source_generator.process_string_field(
            field_name, doc_string, nullable
        )
        self.marshal_c_to_lcm_source_generator.process_string_field(
            field_name, doc_string, nullable
        )
        self.test_marshal_aspn23_c_generator.process_string_field(
            field_name, doc_string, nullable
        )

    def process_string_array_field(
        self, field_name: str, doc_string: str, nullable: bool = False
    ):
        self.marshal_lcm_to_c_source_generator.process_string_array_field(
            field_name, doc_string, nullable
        )
        self.marshal_c_to_lcm_source_generator.process_string_array_field(
            field_name, doc_string, nullable
        )
        self.test_marshal_aspn23_c_generator.process_string_array_field(
            field_name, doc_string, nullable
        )

    def process_simple_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        self.marshal_lcm_to_c_source_generator.process_simple_field(
            field_name, field_type_name, doc_string, nullable
        )
        self.marshal_c_to_lcm_source_generator.process_simple_field(
            field_name, field_type_name, doc_string, nullable
        )
        self.test_marshal_aspn23_c_generator.process_simple_field(
            field_name, field_type_name, doc_string, nullable
        )

    def process_class_docstring(self, doc_string: str, nullable: bool = False):
        self.marshal_lcm_to_c_source_generator.process_class_docstring(
            doc_string, nullable
        )
        self.marshal_c_to_lcm_source_generator.process_class_docstring(
            doc_string, nullable
        )
        self.test_marshal_aspn23_c_generator.process_class_docstring(
            doc_string, nullable
        )

    def process_inheritance_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        self.marshal_lcm_to_c_source_generator.process_inheritance_field(
            field_name, field_type_name, doc_string, nullable
        )
        self.marshal_c_to_lcm_source_generator.process_inheritance_field(
            field_name, field_type_name, doc_string, nullable
        )
        self.test_marshal_aspn23_c_generator.process_inheritance_field(
            field_name, field_type_name, doc_string, nullable
        )

    def process_enum(
        self,
        field_name: str,
        field_type_name: str,
        enum_values: List[str],
        doc_string: str,
        enum_values_doc_strs: List[str],
    ):
        self.marshal_lcm_to_c_source_generator.process_enum(
            field_name,
            field_type_name,
            enum_values,
            doc_string,
            enum_values_doc_strs,
        )
        self.marshal_c_to_lcm_source_generator.process_enum(
            field_name,
            field_type_name,
            enum_values,
            doc_string,
            enum_values_doc_strs,
        )
        self.test_marshal_aspn23_c_generator.process_enum(
            field_name,
            field_type_name,
            enum_values,
            doc_string,
            enum_values_doc_strs,
        )

    def generate(self):
        self.marshal_lcm_to_c_source_generator.generate()
        self.marshal_c_to_lcm_source_generator.generate()
        self.test_marshal_aspn23_c_generator.generate()

        self._generate_from_header()
        self._generate_to_header()
