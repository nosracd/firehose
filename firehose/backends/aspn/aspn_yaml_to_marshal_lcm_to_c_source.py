from os.path import join
from textwrap import dedent
from typing import List, Union
from firehose.backends import Backend
from firehose.backends.aspn.utils import (
    format_and_write_to_file,
    ASPN_PREFIX,
    snake_to_pascal,
    pascal_to_snake,
)


class Struct:
    def __init__(self, snake_case_struct_name: str):
        self.struct_docstr: str = "<Missing C Docstring>"
        self.struct_name: str = (
            f"Aspn{snake_to_pascal(snake_case_struct_name)}"
        )
        self.struct_name_lcm: str = f"aspn23_lcm_{snake_case_struct_name}"
        self.struct_enum: str = f"ASPN_{snake_case_struct_name}".upper()
        self.fn_basename: str = f"aspn_{snake_case_struct_name}".lower()
        self.function_args: List[str] = []
        self.function_prep_buf: List[str] = []
        self.function_free_buf: List[str] = []
        self.function_new_template = dedent(f"""
                {self.struct_name}* out = {self.fn_basename}_new({{function_args}});
        """)
        self.function_template = dedent(f"""
            {self.struct_name}* marshal_{self.struct_name_lcm}({self.struct_name_lcm}* lcm_msg) {{{{
                {{function_prep}}
                {{function_new}}
                {{function_free}}
                return out;
            }}}}
        """)


class AspnYamlToMarshalLCMToCSource(Backend):
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
        c_file_contents = """/*
         * This code is generated via firehose.
         * DO NOT hand edit code.  Make any changes required using the firehose repo instead
         */
        #include <marshal_from_lcm.h>

        #include <utils/conversions.h>
        #include <utils/logging.h>

        static double* flatten_covariance(double** covariance, int length) {
            if (covariance == NULL || length <= 0) return NULL;
            double* flat_covariance = calloc(length * length, sizeof(double));
            int index               = 0;
            for (int ii = 0; ii < length; ++ii) {
                for (int jj = 0; jj < length; ++jj) {
                    flat_covariance[index++] = covariance[ii][jj];
                }
            }
            return flat_covariance;
        }

        static AspnTypeIntegrity* marshal_aspn23_lcm_type_integrity(aspn23_lcm_type_integrity* integrity, int length) {
            if (integrity == NULL || length <= 0) return NULL;

            AspnTypeIntegrity* out = calloc(length, sizeof(AspnTypeIntegrity));
            for (int ii = 0; ii < length; ii++) {
                out[ii].integrity_method = integrity[ii].integrity_method;
                out[ii].integrity_value  = integrity[ii].integrity_value;
            }
            return out;
        }

        static AspnTypeHeader marshal_aspn23_lcm_type_header(aspn23_lcm_type_header header, Aspn23MessageType type) {
            AspnTypeHeader out = {type,
                                  header.vendor_id,
                                  header.device_id,
                                  header.context_id,
                                  header.sequence_id};
            return out;
        }

        static AspnTypeMetadataheader* marshal_aspn23_lcm_type_metadataheader(aspn23_lcm_type_metadataheader lcm_msg, Aspn23MessageType type) {
            AspnTypeHeader header = marshal_aspn23_lcm_type_header(lcm_msg.header, type);

            AspnTypeMetadataheader* out = aspn_type_metadataheader_new(&header,
                                                                       lcm_msg.sensor_description,
                                                                       lcm_msg.delta_t_nom,
                                                                       lcm_msg.timestamp_clock_id,
                                                                       lcm_msg.digits_of_precision);
            return out;
        }
        """
        for struct in self.structs:
            if (
                struct.struct_name != "AspnTypeIntegrity"
                and struct.struct_name != "AspnTypeHeader"
                and struct.struct_name != "AspnTypeMetadataheader"
            ):
                c_file_contents += struct.function_template.format(
                    function_prep='\n'.join(struct.function_prep_buf),
                    function_new=join(
                        struct.function_new_template.format(
                            function_args=', '.join(struct.function_args)
                        )
                    ),
                    function_free='\n'.join(struct.function_free_buf),
                )
        c_output_filename = join(self.output_folder, "marshal_from_lcm.c")
        format_and_write_to_file(c_file_contents, c_output_filename)

    # Helper Functions #
    def remove_aspn_prefix(self, type_name: str):
        return type_name.replace("Aspn23", "")

    def remove_aspn_version(self, type_name: str):
        return type_name.replace("Aspn23", "Aspn")

    def get_lcm_type_name(self, type_name: str):
        return (
            f"aspn23_lcm_{pascal_to_snake(self.remove_aspn_prefix(type_name))}"
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
        match type_name:
            case "Aspn23TypeIntegrity":
                self.current_struct.function_prep_buf.append(
                    "AspnTypeIntegrity* integrity = marshal_aspn23_lcm_type_integrity(lcm_msg->integrity, lcm_msg->num_integrity);"
                )
                self.current_struct.function_args.append("integrity")
                self.current_struct.function_free_buf.append(
                    "aspn_type_integrity_free(integrity);"
                )
            case "uint8_t":
                if (
                    field_name == "clock_id"
                    or field_name == "descriptor"
                    or field_name == "image_data"
                ):
                    self.current_struct.function_prep_buf.append(
                        f"""uint8_t* {field_name} = calloc(lcm_msg->{data_len}, sizeof(uint8_t));
                        for (int32_t ii = 0; ii < lcm_msg->{data_len}; ii++) {{
                            {field_name}[ii] = (uint8_t)lcm_msg->{field_name}[ii];
                        }}"""
                    )
                    self.current_struct.function_args.append(f"{field_name}")
                    self.current_struct.function_free_buf.append(
                        f"free({field_name});"
                    )
                else:
                    self.current_struct.function_args.append(
                        f"lcm_msg->{field_name}"
                    )
            case (
                "char*"
                | "bool"
                | "double"
                | "float"
                | "uint16_t"
                | "uint32_t"
                | "uint64_t"
                | "int8_t"
                | "int16_t"
                | "int32_t"
                | "int64_t"
            ):
                self.current_struct.function_args.append(
                    f"lcm_msg->{field_name}"
                )
            case _:
                self.current_struct.function_prep_buf.append(
                    f"""{self.remove_aspn_version(type_name)}** {field_name}_pointers = calloc(lcm_msg->{data_len}, sizeof({self.remove_aspn_version(type_name)}*));
                    {self.remove_aspn_version(type_name)}* {field_name} = calloc(lcm_msg->{data_len}, sizeof({self.remove_aspn_version(type_name)}));
                    for (int32_t ii = 0; ii < lcm_msg->{data_len}; ii++) {{
                        {field_name}_pointers[ii] = marshal_{self.get_lcm_type_name(type_name)}(&lcm_msg->{field_name}[ii]);
                        {field_name}[ii] = *{field_name}_pointers[ii];
                    }}"""
                )
                self.current_struct.function_args.append(f"{field_name}")
                self.current_struct.function_free_buf.append(
                    f"""for (int32_t ii = lcm_msg->{data_len} - 1; ii >= 0; ii--) {{
                        aspn_{pascal_to_snake(self.remove_aspn_prefix(type_name))}_free({field_name}_pointers[ii]);
                    }}
                    free({field_name}_pointers);
                    free({field_name});"""
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
            self.current_struct.function_prep_buf.append(
                f"double* flat_{field_name} = flatten_covariance(lcm_msg->{field_name}, lcm_msg->{x});"
            )
            self.current_struct.function_args.append(f"flat_{field_name}")
            self.current_struct.function_free_buf.append(
                f"free(flat_{field_name});"
            )
        else:
            self.current_struct.function_args.append(f"lcm_msg->{field_name}")

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
        match field_type_name:
            case "Aspn23TypeHeader":
                self.current_struct.function_prep_buf.append(
                    f"AspnTypeHeader header = marshal_aspn23_lcm_type_header(lcm_msg->header, {self.current_struct.struct_enum});"
                )
                self.current_struct.function_args.append("&header")
            case "Aspn23TypeTimestamp":
                self.current_struct.function_prep_buf.append(
                    f"AspnTypeTimestamp {field_name} = {{lcm_msg->{field_name}.elapsed_nsec}};"
                )
                self.current_struct.function_args.append(f"&{field_name}")
            case "Aspn23TypeMetadataheader":
                self.current_struct.function_prep_buf.append(
                    f"AspnTypeMetadataheader* {field_name} = marshal_aspn23_lcm_type_metadataheader(lcm_msg->{field_name}, {self.current_struct.struct_enum});"
                )
                self.current_struct.function_args.append(f"{field_name}")
                self.current_struct.function_free_buf.append(
                    f"aspn_type_metadataheader_free({field_name});"
                )
            case "Aspn23TypeImageFeature":
                self.current_struct.function_prep_buf.append(
                    f"""AspnTypeImageFeature* {field_name} = NULL;
                    if (lcm_msg->has_observation_characteristics) {{
                        {field_name} = marshal_aspn23_lcm_type_image_feature(&lcm_msg->{field_name});
                        }}"""
                )
                self.current_struct.function_args.append(f"{field_name}")
                self.current_struct.function_free_buf.append(
                    f"aspn_type_image_feature_free({field_name});"
                )
            case (
                "char*"
                | "bool"
                | "double"
                | "float"
                | "uint8_t"
                | "uint16_t"
                | "uint32_t"
                | "uint64_t"
                | "int8_t"
                | "int16_t"
                | "int32_t"
                | "int64_t"
            ):
                self.current_struct.function_args.append(
                    f"lcm_msg->{field_name}"
                )
            case _:
                self.current_struct.function_prep_buf.append(
                    f"{self.remove_aspn_version(field_type_name)}* {field_name} = marshal_{self.get_lcm_type_name(field_type_name)}(&lcm_msg->{field_name});"
                )
                self.current_struct.function_args.append(f"{field_name}")
                self.current_struct.function_free_buf.append(
                    f"{pascal_to_snake(self.remove_aspn_version(field_type_name))}_free({field_name});"
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
        self.current_struct.function_args.append(f"lcm_msg->{field_name}")
