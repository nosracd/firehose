from firehose.backends import Backend
from firehose.backends.aspn.utils import (
    format_and_write_to_file,
    format_docstring,
    snake_to_pascal,
    ASPN_PREFIX_LOWER,
)
from glob import glob
from os import makedirs, remove
from os.path import join
from textwrap import dedent
from typing import List, Union


class Struct:
    def __init__(self, struct_name: str):
        self.struct_docstr: str = "<Missing ROS Docstring>"
        self.struct_fields_buf: List[str] = []
        self.struct_name: str = struct_name
        self.struct_template = dedent(f"""
            # This code is generated via firehose.
            # DO NOT hand edit code.  Make any changes required using the firehose repo instead

            {{struct_docstr}}

            {{struct_fields}}
            """)


class AspnYamlToROS(Backend):
    current_struct: Struct | None = None
    structs: List[Struct] = []

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = output_root_folder
        msg_dir = f"{self.output_folder}/msg"
        makedirs(msg_dir, exist_ok=True)
        for file in glob(f"{msg_dir}/*.msg"):
            remove(file)

    def begin_struct(self, struct_name):
        if self.current_struct is not None:
            self.structs += [self.current_struct]
        self.current_struct = Struct(struct_name)

    def generate(self):
        if self.current_struct is not None:
            self.structs += [self.current_struct]
        msg_names = []
        for struct in self.structs:
            file_contents = struct.struct_template.format(
                struct_docstr=format_docstring(
                    struct.struct_docstr, style="#"
                ),
                struct_fields="\n\n".join(struct.struct_fields_buf),
            )
            filename = f"{snake_to_pascal(struct.struct_name)}.msg"
            msg_names.append(f"\"msg/{filename}\"")
            output_filename = join(self.output_folder, "msg", filename)
            format_and_write_to_file(file_contents, output_filename)
        msg_names = '\n  '.join(msg_names)
        format_and_write_to_file(
            dedent(f"""\
                cmake_minimum_required(VERSION 3.8)
                project({ASPN_PREFIX_LOWER}_ros_interfaces)

                if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
                  add_compile_options(-Wall -Wextra -Wpedantic)
                endif()

                # find dependencies
                find_package(ament_cmake REQUIRED)
                find_package(rosidl_default_generators REQUIRED)

                rosidl_generate_interfaces({ASPN_PREFIX_LOWER}_ros_interfaces
                  {{msg_names}}
                )

                if(BUILD_TESTING)
                  find_package(ament_lint_auto REQUIRED)
                  ament_lint_auto_find_test_dependencies()
                endif()

                ament_package()\
                """).format(msg_names=msg_names),
            join(self.output_folder, "CMakeLists.txt"),
        )

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
        if data_len and isinstance(data_len, str):
            field_str = f"{type_name}[] {field_name}"
            doc_string += f"\nNote: array length is {data_len}"
        else:
            field_str = f"{type_name}[{data_len}] {field_name}"
        docstr = format_docstring(doc_string, style="#")
        self.current_struct.struct_fields_buf.append(f"{docstr}\n{field_str}")

    def process_matrix_field(
        self,
        field_name: str,
        type_name: str,
        x: Union[str, int],
        y: Union[str, int],
        doc_string: str,
        nullable: bool = False,
    ):
        # Flatten matrices into ROS-friendly 1D arrays
        doc_string += f"\nNote: field represents a {x} x {y} matrix"
        try:
            data_len = int(x) * int(y)
        except ValueError:
            data_len = ""
        self.process_data_pointer_field(
            field_name, type_name, data_len, doc_string, nullable=nullable
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
        docstr = format_docstring(doc_string, style="#")
        self.current_struct.struct_fields_buf.append(
            f"{docstr}\n{field_type_name} {field_name}"
        )

    def process_class_docstring(self, doc_string: str, nullable: bool = False):
        if self.current_struct is not None:
            self.current_struct.struct_docstr = doc_string

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
        for i, enum in enumerate(enum_values):
            val = i
            if len(split := enum.split("=")) > 1:
                val = int(split[1])
                enum = split[0].strip()
            max_int = max(max_int, val)
            enum_tuples.append((f"{enum}={val}", enum_values_doc_strs[i]))
        enum_type = "uint8" if max_int < 256 else "uint16"

        self.process_simple_field(field_name, enum_type, doc_string, nullable)
        for field in enum_tuples:
            self.process_simple_field(field[0], enum_type, field[1], nullable)
