from os.path import join
from textwrap import dedent
from typing import List, Union
from firehose.backends import Backend
from firehose.backends.aspn.utils import (
    format_and_write_to_file,
    ASPN_PREFIX,
    ASPN_PREFIX_LOWER,
    ASPN_PREFIX_UPPER,
    snake_to_pascal,
    pascal_to_snake,
)


class Struct:
    def __init__(self, snake_case_struct_name: str):
        self.struct_docstr: str = "<Missing C Docstring>"
        self.struct_name: str = (
            f"Aspn{snake_to_pascal(snake_case_struct_name)}"
        )
        self.struct_name_versioned: str = (
            f"{ASPN_PREFIX}{snake_to_pascal(snake_case_struct_name)}"
        )
        self.struct_name_lcm: str = (
            f"{ASPN_PREFIX_LOWER}_lcm_{snake_case_struct_name}"
        )
        self.struct_enum: str = f"ASPN_{snake_case_struct_name}".upper()
        self.fn_basename: str = f"aspn_{snake_case_struct_name}".lower()
        self.function_assign_buf: List[str] = []
        self.function_template = dedent(f"""
            void marshal_{self.struct_name_versioned}({self.struct_name_lcm}* lcm_msg, const {self.struct_name}* aspn) {{{{
                {{function_assign}}
            }}}}
        """)


class AspnYamlToMarshalCToLCMSource(Backend):
    def __init__(self):
        self.current_struct: Struct = None
        self.structs: List[Struct] = []

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = output_root_folder
        # Expecting parent AspnCMarshalingBackend to clear output folder

    def begin_struct(self, snake_case_struct_name):
        if self.current_struct is not None:
            self.structs += [self.current_struct]
        self.current_struct = Struct(snake_case_struct_name)

    def generate(self) -> None:
        self.structs += [self.current_struct]
        c_file_contents = f"""/*
         * This code is generated via firehose.
         * DO NOT hand edit code.  Make any changes required using the firehose repo instead
         */
        #include <marshal_to_lcm.h>
        #include <glib.h>
        #include <utils/conversions.h>
        #include <utils/get_time.h>

        static double** unflatten_covariance(double* flat_covariance, size_t length) {{
            if (flat_covariance == NULL || length == 0) return NULL;
            double** out = (double**)malloc(length * sizeof(double*));
            for (size_t row = 0; row < length; ++row) {{
                out[row] = (double*)malloc(length * sizeof(double));
                for (size_t col = 0; col < length; ++col) {{
                    out[row][col] = flat_covariance[row * length + col];
                }}
            }}
            return out;
        }}

        static void marshal_{ASPN_PREFIX}TypeHeader({ASPN_PREFIX_LOWER}_lcm_type_header* lcm_msg, const AspnTypeHeader* aspn) {{
            lcm_msg->vendor_id   = aspn->vendor_id;
            lcm_msg->device_id   = aspn->device_id;
            lcm_msg->context_id  = aspn->context_id;
            lcm_msg->sequence_id = aspn->sequence_id;
        }}

        static void marshal_{ASPN_PREFIX}TypeMetadataheader({ASPN_PREFIX_LOWER}_lcm_type_metadataheader* lcm_msg, const AspnTypeMetadataheader* aspn) {{
            marshal_{ASPN_PREFIX}TypeHeader(&lcm_msg->header, &aspn->header);
            if (aspn->sensor_description != NULL) {{
                size_t len = strlen(aspn->sensor_description) + 1;
                lcm_msg->sensor_description = calloc(len, sizeof(char));
                memcpy(lcm_msg->sensor_description, aspn->sensor_description, len);
            }}
            lcm_msg->delta_t_nom         = aspn->delta_t_nom;
            lcm_msg->timestamp_clock_id  = aspn->timestamp_clock_id;
            lcm_msg->digits_of_precision = aspn->digits_of_precision;
        }}

        static {ASPN_PREFIX_LOWER}_lcm_type_integrity* marshal_{ASPN_PREFIX}TypeIntegrity(AspnTypeIntegrity* integrity, size_t length) {{
            if (integrity == NULL || length == 0) return NULL;
            {ASPN_PREFIX_LOWER}_lcm_type_integrity* out = calloc(length, sizeof({ASPN_PREFIX_LOWER}_lcm_type_integrity));
            for (size_t ii = 0; ii < length; ii++) {{
                out[ii].integrity_method = integrity[ii].integrity_method;
                out[ii].integrity_value  = integrity[ii].integrity_value;
            }}
            return out;
        }}

        """
        for struct in self.structs:
            if (
                struct.struct_name != "AspnTypeIntegrity"
                and struct.struct_name != "AspnTypeHeader"
                and struct.struct_name != "AspnTypeMetadataheader"
            ):
                c_file_contents += struct.function_template.format(
                    function_assign='\n'.join(struct.function_assign_buf)
                )
        c_output_filename = join(self.output_folder, "marshal_to_lcm.c")
        format_and_write_to_file(c_file_contents, c_output_filename)

    # Helper Functions #
    def remove_aspn_prefix(self, type_name: str):
        return type_name.replace(ASPN_PREFIX, "")

    def remove_aspn_version(self, type_name: str):
        if ASPN_PREFIX_LOWER in type_name:
            return type_name.replace(ASPN_PREFIX_LOWER, "aspn")
        if ASPN_PREFIX in type_name:
            return type_name.replace(ASPN_PREFIX, "Aspn")
        if ASPN_PREFIX_UPPER in type_name:
            return type_name.replace(ASPN_PREFIX_UPPER, "ASPN")

    def get_lcm_type_name(self, type_name: str):
        return f"{ASPN_PREFIX_LOWER}_lcm_{pascal_to_snake(self.remove_aspn_prefix(type_name))}"

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
        if isinstance(data_len, str):
            if data_len.isdigit():
                length = data_len
                assign = f"memcpy(lcm_msg->{field_name}, aspn->{field_name}, {length} * sizeof({type_name}));"
            else:
                length = f"aspn->{data_len}"
                assign = f"""if (aspn->{field_name} != NULL && {length} != 0) {{
                    lcm_msg->{field_name} = calloc({length}, sizeof({type_name}));
                    memcpy(lcm_msg->{field_name}, aspn->{field_name}, {length} * sizeof({type_name}));
                }}"""
        else:
            length = data_len
            assign = f"memcpy(lcm_msg->{field_name}, aspn->{field_name}, {length} * sizeof({type_name}));"
        if type_name == f"{ASPN_PREFIX}TypeIntegrity":
            self.current_struct.function_assign_buf.append(
                f"lcm_msg->integrity = marshal_{type_name}(aspn->integrity, aspn->num_integrity);"
            )
        elif type_name == "uint8_t":
            # self.current_struct.function_assign_buf.append(assign)
            if (
                field_name == "clock_id"
                or field_name == "descriptor"
                or field_name == "image_data"
            ):
                self.current_struct.function_assign_buf.append(
                    f"""if (aspn->{field_name} != NULL && {length} != 0) {{
                        lcm_msg->{field_name} = calloc({length}, sizeof(int16_t));
                        for (size_t ii = 0; ii < {length}; ii++) {{
                            lcm_msg->{field_name}[ii] = aspn->{field_name}[ii];
                        }}
                    }}"""
                )
            else:
                self.current_struct.function_assign_buf.append(assign)
        elif type_name in [
            "char*",
            "bool",
            "double",
            "float",
            "uint16_t",
            "uint32_t",
            "uint64_t",
            "int8_t",
            "int16_t",
            "int32_t",
            "int64_t",
        ]:
            self.current_struct.function_assign_buf.append(assign)
        else:
            self.current_struct.function_assign_buf.append(
                f"""lcm_msg->{field_name} = calloc({length}, sizeof({self.get_lcm_type_name(type_name)}));
                for (uint32_t ii = 0; ii < {length}; ii++) {{
                    marshal_{type_name}(&lcm_msg->{field_name}[ii], &aspn->{field_name}[ii]);
                }}"""
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
        if (
            (not isinstance(x, int))
            and field_name == "covariance"
            or field_name == "position_covariance"
            or field_name == "k"
        ):
            self.current_struct.function_assign_buf.append(
                f"lcm_msg->{field_name} = unflatten_covariance(aspn->{field_name}, aspn->{x});"
            )
        else:
            self.current_struct.function_assign_buf.append(
                f"memcpy(lcm_msg->{field_name}, aspn->{field_name}, {x} * {y} * sizeof({type_name}));"
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
            field_name, "char*", doc_string, nullable=nullable
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
        if field_type_name == f"{ASPN_PREFIX}TypeImageFeature":
            self.current_struct.function_assign_buf.append(
                f"""if (aspn->has_observation_characteristics) {{
                    marshal_{field_type_name}(&lcm_msg->{field_name}, &aspn->{field_name});
                    }}"""
            )
        elif field_type_name in [
            "char*",
            "bool",
            "double",
            "float",
            "uint8_t",
            "uint16_t",
            "uint32_t",
            "uint64_t",
            "int8_t",
            "int16_t",
            "int32_t",
            "int64_t",
        ]:
            self.current_struct.function_assign_buf.append(
                f"lcm_msg->{field_name} = aspn->{field_name};"
            )
        else:
            self.current_struct.function_assign_buf.append(
                f"marshal_{field_type_name}(&lcm_msg->{field_name}, &aspn->{field_name});"
            )

    def process_inheritance_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        raise NotImplementedError

    def process_class_docstring(self, doc_string: str, nullable: bool = False):
        self.current_struct.struct_docstr = doc_string
        pass

    def process_enum(
        self,
        field_name: str,
        field_type_name: str,
        enum_values: List[str],
        doc_string: str,
        enum_values_doc_strs: List[str],
        nullable: bool = False,
    ):
        self.current_struct.function_assign_buf.append(
            f"lcm_msg->{field_name} = aspn->{field_name};"
        )
