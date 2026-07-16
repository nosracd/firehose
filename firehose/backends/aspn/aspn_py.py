from shutil import rmtree
from os.path import join
from typing import List, Tuple, Union, Dict, Set
from ..backend import Backend
from .aspn_yaml_to_python import AspnYamlToPython
from .utils import ASPN_PREFIX_LOWER


class AspnPyBackend(Backend):
    def __init__(self):
        self.generators = [AspnYamlToPython()]

    def _remove_existing_output_files(self):
        rmtree(self.output_folder, ignore_errors=True)

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = join(output_root_folder, 'src', ASPN_PREFIX_LOWER)
        self._remove_existing_output_files()
        for generator in self.generators:
            generator.set_output_root_folder(self.output_folder)

    def begin_struct(self, struct_name: str):
        for generator in self.generators:
            self.struct_name = struct_name
            generator.begin_struct(self.struct_name)

    def process_func_ptr_field_with_self(
        self,
        field_name: str,
        params,
        return_t,
        doc_string: str,
        nullable: bool = False,
    ):
        for generator in self.generators:
            generator.process_func_ptr_field_with_self(
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
        for generator in self.generators:
            generator.process_data_pointer_field(
                field_name, type_name, data_len, doc_string, deref, nullable
            )

    def process_matrix_field(
        self,
        field_name: str,
        type_name: str,
        x: int,
        y: int,
        doc_string: str,
        nullable: bool = False,
    ):
        for generator in self.generators:
            generator.process_matrix_field(
                field_name, type_name, x, y, doc_string, nullable
            )

    def process_outer_managed_pointer_field(
        self, field_name: str, field_type_name: str, doc_string: str
    ):
        for generator in self.generators:
            generator.process_outer_managed_pointer_field(
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
        for generator in self.generators:
            generator.process_outer_managed_pointer_array_field(
                field_name,
                field_type_name,
                data_len,
                doc_string,
                deref,
                nullable,
            )

    def process_string_field(
        self, field_name: str, doc_string: str, nullable: bool = False
    ):
        for generator in self.generators:
            generator.process_string_field(field_name, doc_string, nullable)

    def process_string_array_field(
        self, field_name: str, doc_string: str, nullable: bool = False
    ):
        for generator in self.generators:
            generator.process_string_array_field(
                field_name, doc_string, nullable
            )

    def process_simple_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        for generator in self.generators:
            generator.process_simple_field(
                field_name, field_type_name, doc_string, nullable
            )

    def process_class_docstring(self, doc_string: str, nullable: bool = False):
        for generator in self.generators:
            generator.process_class_docstring(doc_string, nullable)

    def process_inheritance_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        for generator in self.generators:
            generator.process_inheritance_field(
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
        for generator in self.generators:
            generator.process_enum(
                field_name,
                field_type_name,
                enum_values,
                doc_string,
                enum_values_doc_strs,
            )

    def generate(self):
        for generator in self.generators:
            generator.generate()
