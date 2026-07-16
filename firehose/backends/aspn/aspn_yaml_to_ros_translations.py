from os import makedirs, remove, path
from os.path import join
from textwrap import dedent
from typing import List, Union

from firehose.backends import Backend
from firehose.backends.aspn.utils import (
    ASPN_PREFIX_LOWER,
    INDENT,
    format_and_write_to_file,
    is_length_field,
    pascal_to_snake,
    snake_to_pascal,
)

PRIMITIVES = ["float", "int", "bool", "str"]


class Struct:
    def __init__(self, snake_struct_name: str, to_ros: bool = True):
        self.struct_name: str = snake_to_pascal(snake_struct_name)
        self.to_ros: bool = to_ros
        self.assignments: list[str] = []
        self.imports_enum: set[str] = set()
        self.to_ros_template: str = dedent(f"""\
            def {pascal_to_snake(self.struct_name)}_to_ros(old: {self.struct_name}) -> Ros{self.struct_name}:
            {INDENT}msg = Ros{self.struct_name}()
            {{assigns}}

            {INDENT}return msg
            """)
        self.from_ros_template = dedent(f"""\
            def ros_to_{snake_struct_name}(old: Ros{self.struct_name}) -> {self.struct_name}:
            {INDENT}return {self.struct_name}({{assigns}})
            """)


class AspnYamlToROSTranslations(Backend):
    current_struct: Struct | None = None
    structs: List[Struct] = []
    output_folder = None

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = output_root_folder
        makedirs(self.output_folder, exist_ok=True)
        if self.output_folder is not None:
            filename = f"{self.output_folder}/ros_translations.py"
            if path.exists(filename):
                remove(filename)

    def begin_struct(self, struct_name, to_ros: bool = False):
        if self.current_struct is not None:
            self.structs += [self.current_struct]
        self.current_struct = Struct(struct_name, to_ros)

    def generate(self):
        if self.output_folder is None:
            return
        if self.current_struct is not None:
            self.structs += [self.current_struct]

        imports_aspn = []
        imports_ros = []
        functions = []
        exports = []
        alias_aspn = []
        alias_ros = []
        to_ros_map = []
        from_ros_map = []
        for s in self.structs:
            # Function assignments to ROS
            if s.to_ros:
                assignments = [f"{INDENT}msg.{a}" for a in s.assignments]
                functions.append(
                    s.to_ros_template.format(assigns="\n".join(assignments))
                )
                continue

            # Function assignments from ROS
            assignments = [f"{INDENT}{INDENT}{a}" for a in s.assignments]
            functions.append(
                s.from_ros_template.format(assigns=", ".join(assignments))
            )

            # Imports/exports/etc. only need to happen once, so skip them for
            # the "to ROS" structs (see above)
            snake_name = pascal_to_snake(s.struct_name)
            imports_aspn.append(
                f"from {ASPN_PREFIX_LOWER}.{snake_name} import {s.struct_name}"
            )
            imports_aspn.extend(s.imports_enum)
            imports_ros.append(
                f"from {ASPN_PREFIX_LOWER}_ros_interfaces.msg import {s.struct_name} as "
                f"Ros{s.struct_name}"
            )
            exports.append(f"ros_to_{snake_name} as ros_to_{snake_name}")
            exports.append(f"{snake_name}_to_ros as {snake_name}_to_ros")

            # For Measurement/Metadata objects, we also want to generate some
            # utility definitions
            if s.struct_name.startswith("Type"):
                continue
            alias_aspn.append(f"{INDENT}{s.struct_name},")
            alias_ros.append(f"{INDENT}Ros{s.struct_name},")
            to_ros_map.append(f"{INDENT}{s.struct_name}: {snake_name}_to_ros,")
            from_ros_map.append(
                f"{INDENT}Ros{s.struct_name}: ros_to_{snake_name},"
            )

        imports = "\n".join(imports_aspn + imports_ros)
        functions = "\n".join(functions)
        exports = "\n".join(exports)
        alias_aspn = "\n".join(alias_aspn)
        alias_ros = "\n".join(alias_ros)
        to_ros_map = "\n".join(to_ros_map)
        from_ros_map = "\n".join(from_ros_map)

        format_and_write_to_file(
            dedent("""\
                from typing import TypeAlias, Union, Callable
                import numpy as np

                {imports}

                {functions}

                AspnMsg: TypeAlias = Union[
                {alias_aspn}
                ]

                RosMsg: TypeAlias = Union[
                {alias_ros}
                ]

                to_ros_map: dict[type[AspnMsg], Callable] = {{
                {to_ros_map}
                }}

                from_ros_map: dict[type[RosMsg], Callable] = {{
                {from_ros_map}
                }}\
                """).format(
                imports=imports,
                alias_aspn=alias_aspn,
                alias_ros=alias_ros,
                functions=functions,
                to_ros_map=to_ros_map,
                from_ros_map=from_ros_map,
            ),
            join(self.output_folder, "ros_translations.py"),
        )

        format_and_write_to_file(
            dedent("""\
                # Follow Python export conventions:
                # https://typing.readthedocs.io/en/latest/spec/distributing.html#import-conventions
                from .aspn_ros_node import AspnRosNode as AspnRosNode
                from .ros_translations import (
                    AspnMsg, RosMsg, to_ros_map, from_ros_map
                )
                from .ros_translations import (
                {exports}
                )\
                """).format(exports=exports),
            join(self.output_folder, "__init__.py"),
        )

    def _add_missing_len_field(
        self, field_name: str, data_len: Union[str, int], nullable: bool
    ):
        if self.current_struct is None or not self.current_struct.to_ros:
            return
        if not isinstance(data_len, str):
            return
        # Skip redundant assignments (caused by multiple arrays with the
        # same variable length)
        if any(
            a.startswith(data_len) for a in self.current_struct.assignments
        ):
            return
        qualifier = ""
        if nullable:
            qualifier = f" if old.{field_name} is not None else 0"
        self.current_struct.assignments.append(
            f"{data_len} = len(old.{field_name})" + qualifier
        )

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

        if self.current_struct.to_ros:
            qualifier = ""
            if nullable:
                qualifier = f" if old.{field_name} is not None else []"
            # Fixed-length arrays can be np.arrays or lists in rospy
            if isinstance(data_len, int):
                self.current_struct.assignments.append(
                    f"{field_name} = old.{field_name}" + qualifier
                )
            # Variable-length arrays must be lists in rospy
            elif type_name in PRIMITIVES:
                self.current_struct.assignments.append(
                    f"{field_name} = old.{field_name}.tolist()" + qualifier
                )
            else:  # Handle lists of non-primitives
                self.current_struct.assignments.append(
                    f"{field_name} = [{pascal_to_snake(type_name)}_to_ros(x) "
                    f"for x in old.{field_name}]" + qualifier
                )
        else:  # aspn-ros-py -> aspn-py
            # Make sure lists of primitives in rospy become np.arrays
            if isinstance(data_len, int) or type_name in PRIMITIVES:
                self.current_struct.assignments.append(
                    f"{field_name} = np.array(old.{field_name})"
                )
            else:  # Handle lists of non-primitives
                self.current_struct.assignments.append(
                    f"{field_name} = [ros_to_{pascal_to_snake(type_name)}(x) "
                    f"for x in old.{field_name}]"
                )
        self._add_missing_len_field(field_name, data_len, nullable)

    def process_matrix_field(
        self,
        field_name: str,
        type_name: str,
        x: int | str,
        y: int | str,
        doc_string: str,
        nullable: bool = False,
    ):
        if self.current_struct is None:
            return
        if x != y:
            raise NotImplementedError
        self._add_missing_len_field(field_name, x, nullable)

        if self.current_struct.to_ros:
            qualifier = ""
            if nullable:
                qualifier = f" if old.{field_name} is not None else []"
            self.current_struct.assignments.append(
                f"{field_name} = old.{field_name}.flatten().tolist()"
                + qualifier
            )
        else:
            x = "old." + x if isinstance(x, str) else x
            y = "old." + y if isinstance(y, str) else y
            self.current_struct.assignments.append(
                f"{field_name} = np.array(old.{field_name}).reshape({x}, {y})"
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
            field_name, "str", doc_string, nullable=nullable
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
        if is_length_field(field_name):
            return

        if self.current_struct.to_ros:
            qualifier = ""
            if field_type_name in PRIMITIVES:
                if nullable:
                    # ROS cannot handle None fields, so these must be
                    # default-initalized
                    qualifier = (
                        f" if old.{field_name} is not None else "
                        f"{field_type_name}()"
                    )
                self.current_struct.assignments.append(
                    f"{field_name} = old.{field_name}" + qualifier
                )
            else:
                if nullable:
                    qualifier = (
                        f" if old.{field_name} is not None else "
                        f"Ros{field_type_name}()"
                    )
                self.current_struct.assignments.append(
                    f"{field_name} = {pascal_to_snake(field_type_name)}"
                    f"_to_ros(old.{field_name})" + qualifier
                )
        else:
            if field_type_name in PRIMITIVES:
                self.current_struct.assignments.append(
                    f"{field_name} = old.{field_name}"
                )
            else:
                self.current_struct.assignments.append(
                    f"{field_name} = ros_to_{pascal_to_snake(field_type_name)}"
                    f"(old.{field_name})"
                )

    def process_class_docstring(self, doc_string: str, nullable=None):
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
    ):
        if self.current_struct is None:
            return

        if self.current_struct.to_ros:
            self.current_struct.assignments.append(
                f"{field_name} = old.{field_name}.value"
            )
        else:
            struct_name = pascal_to_snake(self.current_struct.struct_name)
            field_type_name = (
                f"{self.current_struct.struct_name}"
                f"{snake_to_pascal(field_type_name)}"
            )
            self.current_struct.imports_enum.add(
                f"from {ASPN_PREFIX_LOWER}.{struct_name} import {field_type_name}"
            )
            self.current_struct.assignments.append(
                f"{field_name} = {field_type_name}(old.{field_name})"
            )
