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
import random

random.seed(82396)


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
        self.function_from_prep_buf: List[str] = []
        self.function_to_prep_buf: List[str] = []
        self.function_free_buf: List[str] = []
        self.function_test_buf: List[str] = []
        self.create_basic_lcm_type_function_declaration_template = dedent(f"""
            static {self.struct_name_lcm} create_basic_{self.struct_name_lcm}(void);
        """)
        self.free_basic_lcm_type_function_declaration_template = dedent(f"""
            static void free_basic_{self.struct_name_lcm}({self.struct_name_lcm}* lcm_msg);
        """)
        self.type_test_declaration_template = dedent(f"""
            static void test_marshal_{self.struct_name_versioned}({self.struct_name_lcm}* lcm_msg, {self.struct_name}* aspn);
        """)
        self.create_basic_c_type_function_declaration_template = dedent(f"""
            static {self.struct_name} create_basic_{self.struct_name}(void);
        """)
        self.create_basic_lcm_type_function_template = dedent(f"""
            static {self.struct_name_lcm} create_basic_{self.struct_name_lcm}(void) {{{{
                {self.struct_name_lcm} lcm_msg;
                {{function_prep}}
                return lcm_msg;
            }}}}
        """)
        self.free_basic_lcm_type_function_template = dedent(f"""
            static void free_basic_{self.struct_name_lcm}({self.struct_name_lcm}* lcm_msg) {{{{
                {{function_free}}
            }}}}
        """)
        self.type_test_function_template = dedent(f"""
            static void test_marshal_{self.struct_name_versioned}({self.struct_name_lcm}* lcm_msg, {self.struct_name}* aspn) {{{{
                {{function_test}}
            }}}}
        """)
        self.create_basic_c_type_function_template = dedent(f"""
            static {self.struct_name} create_basic_{self.struct_name}(void) {{{{
                {self.struct_name} aspn;
                {{function_prep}}
                return aspn;
            }}}}
        """)
        self.run_test_from_function_template = dedent(
            f"g_test_add_func(\"/lcm_{ASPN_PREFIX_LOWER}_transport_plugin/test_marshal_{self.struct_name_lcm}\", test_marshal_{self.struct_name_lcm});"
        )
        self.run_test_to_function_template = dedent(
            f"g_test_add_func(\"/lcm_{ASPN_PREFIX_LOWER}_transport_plugin/test_marshal_{self.struct_name_versioned}\", test_marshal_{self.struct_name_versioned});"
        )
        self.test_from_function_template = dedent(f"""
            static void test_marshal_{self.struct_name_lcm}(void) {{{{
                {self.struct_name_lcm}* lcm_msg = malloc(sizeof({self.struct_name_lcm}));
                {{function_prep}}
                {self.struct_name}* aspn = marshal_{self.struct_name_lcm}(lcm_msg);
                {{function_test}}
                {{function_free}}
                free(lcm_msg);
                {self.fn_basename}_free(aspn);
            }}}}
        """)
        self.test_to_function_template = dedent(f"""
            static void test_marshal_{self.struct_name_versioned}(void) {{{{
                {self.struct_name}* aspn = malloc(sizeof({self.struct_name}));
                {{function_prep}}
                {self.struct_name_lcm}* lcm_msg = malloc(sizeof({self.struct_name_lcm}));
                marshal_{self.struct_name_versioned}(lcm_msg, aspn);
                {{function_test}}
                {{function_free}}
                free(lcm_msg);
                {self.fn_basename}_free(aspn);
            }}}}
        """)


class AspnYamlToTestMarshalAspn23(Backend):
    def __init__(self):
        self.current_struct: Struct = None
        self.structs: List[Struct] = []

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = output_root_folder
        # Expecting parent AspnCBackend to clear output folder

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
        #include "test_lcm_aspn23_plugin.h"
        #include <marshal_from_lcm.h>
        #include <marshal_to_lcm.h>

        #include <glib.h>
        #include <math.h>
        #include <aspn.h>
        #include <stdio.h>
        #include <test_common.h>
        #include <test_common_dynamic.h>

        typedef struct TestFixture {
            char* plugin_path;         // full path to plugin
            char* registry;            // full path to registry plugin
            char* registry_init_file;  // constructed full path to registry init_file
        } TestFixture;

        static void test_fixture_setup(TestFixture* fixture, gconstpointer user_data) {
            // Meson will pass in env variables for this test to set itself up
            // The path of the plugin we are testing, in this case example_plugin_transport
            fixture->plugin_path = g_strconcat(g_getenv("G_TEST_EXAMPLE_PLUGIN"), NULL);
            // The registry plugin we are using, this is determined from meson and is the full path
            // to the plugin in the build/ directory
            fixture->registry = g_strconcat(g_getenv("G_TEST_REFERENCE_REGISTRY"), NULL);
            if (fixture->plugin_path == NULL || fixture->registry == NULL) {
                printf("parsing of env variables failed in one or more cases, exiting\\n");
                // force to exit without seg faulting
                g_assert_true(false);
            }

            // init file if we have it, in this test suite we don't use one
            // as lcm_transport will gracefully handle NULL values by using
            // defaults in lcm_transport_star
            // if we passed in /test_resources/something.cfg this would work
            fixture->registry_init_file = g_strconcat(g_getenv("G_TEST_SRCDIR"), user_data, NULL);
        }
        static void test_fixture_teardown(TestFixture* fixture, UNUSED gconstpointer user_data) {
            // free up char* file names so we don't get ASAN warning about leaks
            g_free(fixture->plugin_path);
            g_free(fixture->registry);
            g_free(fixture->registry_init_file);
        }

        static void test_init_shutdown_real_registry(TestFixture* fixture, UNUSED gconstpointer user_data) {
            g_assert_true(test_get_init_shutdown(
                fixture->plugin_path, fixture->registry, fixture->registry_init_file));
        }

        // Declare static functions to fix ordering problem
        """
        test_from_functions = ""
        test_to_functions = "// aspn c -> aspn lcm-c"
        run_tests = """
        void test_lcm_aspn23_plugin(void) {
            // When we iterate on our plugin, if any plugin methods use the registry we cannot
            // // use the registry if the registry location was NULL as passed to test_common_dynamic
            g_test_add("/lcm_aspn23_transport_plugin/test_init_shutdown",
                       TestFixture,
                       NULL,
                       test_fixture_setup,
                       test_init_shutdown_real_registry,
                       test_fixture_teardown);
        """
        no_alloc_types = [
            "AspnTypeIntegrity",
            "AspnTypeSatnavSatelliteSystem",
            "AspnTypeSatnavSignalDescriptor",
            "AspnTypeHeader",
            "AspnTypeKeplerOrbit",
            "AspnTypeMounting",
            "AspnTypeSatnavClock",
            "AspnTypeSatnavTime",
            "AspnTypeTimestamp",
            "AspnTypeSatnavSvData",
        ]
        for struct in self.structs:
            if struct.struct_name != "AspnMessageType":
                if "Type" in struct.struct_name:
                    c_file_contents += (
                        struct.create_basic_lcm_type_function_declaration_template.format()
                    )
                    c_file_contents += (
                        struct.type_test_declaration_template.format()
                    )
                    if struct.struct_name not in no_alloc_types:
                        c_file_contents += (
                            struct.free_basic_lcm_type_function_declaration_template.format()
                        )
                    c_file_contents += (
                        struct.create_basic_c_type_function_declaration_template.format()
                    )
                    test_from_functions += (
                        struct.create_basic_lcm_type_function_template.format(
                            function_prep='\n'.join(
                                struct.function_from_prep_buf
                            )
                        )
                    )
                    test_from_functions += (
                        struct.type_test_function_template.format(
                            function_test='\n'.join(struct.function_test_buf)
                        )
                    )
                    if struct.struct_name not in no_alloc_types:
                        test_from_functions += struct.free_basic_lcm_type_function_template.format(
                            function_free='\n'.join(struct.function_free_buf)
                        )
                    test_to_functions += (
                        struct.create_basic_c_type_function_template.format(
                            function_prep='\n'.join(
                                struct.function_to_prep_buf
                            )
                        )
                    )
                else:
                    test_from_functions += (
                        struct.test_from_function_template.format(
                            function_prep='\n'.join(
                                struct.function_from_prep_buf
                            ),
                            function_test='\n'.join(struct.function_test_buf),
                            function_free='\n'.join(struct.function_free_buf),
                        )
                    )
                    run_tests += (
                        struct.run_test_from_function_template.format()
                    )
                    test_to_functions += (
                        struct.test_to_function_template.format(
                            function_prep='\n'.join(
                                struct.function_to_prep_buf
                            ),
                            function_test='\n'.join(struct.function_test_buf),
                            function_free='\n'.join(struct.function_free_buf),
                        )
                    )
                    run_tests += struct.run_test_to_function_template.format()
        c_file_contents += (
            test_from_functions + test_to_functions + run_tests + "\n}\n"
        )
        c_output_filename = join(
            self.output_folder, "test_lcm_aspn23_plugin.c"
        )
        format_and_write_to_file(c_file_contents, c_output_filename)
        c_header_file_contents = """/*
         * This code is generated via firehose.
         * DO NOT hand edit code.  Make any changes required using the firehose repo instead
         */
        #pragma once

        void test_lcm_aspn23_plugin(void);
        """
        c_header_output_filename = join(
            self.output_folder, "test_lcm_aspn23_plugin.h"
        )
        format_and_write_to_file(
            c_header_file_contents, c_header_output_filename
        )

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
        data_len: int,
        doc_string: str,
        deref="",
        nullable: bool = False,
    ):
        get = (
            "."
            if self.current_struct.struct_name.startswith("AspnType")
            else "->"
        )
        if isinstance(data_len, str):
            if data_len.isdigit():
                length = data_len
                c_length = data_len
                test_length = data_len
                prep = f"""for (int32_t ii = 0; ii < {length}; ii++) {{{{
                    lcm_msg{get}{field_name}[ii] = {{assign_rvalue}};
                }}}}"""
                c_prep = f"""for (size_t ii = 0; ii < {c_length}; ii++) {{{{
                    aspn{get}{field_name}[ii] = {{assign_rvalue}};
                }}}}"""
                free = ""
            else:
                if type_name == "uint8_t":
                    length = f"lcm_msg{get}{data_len}"
                    c_length = f"aspn{get}{data_len}"
                    test_length = f"lcm_msg->{data_len}"
                    prep = f"""lcm_msg{get}{field_name} = malloc({length} * sizeof(int16_t));
                        for (int32_t ii = 0; ii < {length}; ii++) {{{{
                            lcm_msg{get}{field_name}[ii] = {{assign_rvalue}};
                        }}}}"""
                    c_prep = f"""aspn{get}{field_name} = malloc({c_length} * sizeof(uint8_t));
                        for (size_t ii = 0; ii < {c_length}; ii++) {{{{
                            aspn{get}{field_name}[ii] = {{assign_rvalue}};
                        }}}}"""
                    free = f"free(lcm_msg->{field_name});"
                else:
                    length = f"lcm_msg{get}{data_len}"
                    c_length = f"aspn{get}{data_len}"
                    test_length = f"lcm_msg->{data_len}"
                    prep = f"""lcm_msg{get}{field_name} = malloc({length} * sizeof({type_name}));
                        for (int32_t ii = 0; ii < {length}; ii++) {{{{
                            lcm_msg{get}{field_name}[ii] = {{assign_rvalue}};
                        }}}}"""
                    c_prep = f"""aspn{get}{field_name} = malloc({c_length} * sizeof({type_name}));
                        for (size_t ii = 0; ii < {c_length}; ii++) {{{{
                            aspn{get}{field_name}[ii] = {{assign_rvalue}};
                        }}}}"""
                    free = f"free(lcm_msg->{field_name});"
        else:
            length = data_len
            c_length = data_len
            test_length = data_len
            prep = f"""for (int32_t ii = 0; ii < {length}; ii++) {{{{
                lcm_msg{get}{field_name}[ii] = {{assign_rvalue}};
            }}}}"""
            c_prep = f"""for (size_t ii = 0; ii < {c_length}; ii++) {{{{
                aspn{get}{field_name}[ii] = {{assign_rvalue}};
            }}}}"""
            free = ""
        match type_name:
            case "char*":
                self.current_struct.function_from_prep_buf.append(
                    prep.format(assign_rvalue="abcdef")
                )
                self.current_struct.function_to_prep_buf.append(
                    c_prep.format(assign_rvalue="abcdef")
                )
                self.current_struct.function_test_buf.append(
                    f"""for (int32_t ii = 0; ii < {test_length}; ii++) {{
                        g_assert_cmpstr(lcm_msg->{field_name}[ii], ==, aspn->{field_name}[ii]);
                    }}"""
                )
                self.current_struct.function_free_buf.append(free)
            case "bool":
                self.current_struct.function_from_prep_buf.append(
                    prep.format(assign_rvalue=random.randint(0, 1))
                )
                self.current_struct.function_to_prep_buf.append(
                    c_prep.format(assign_rvalue=random.randint(0, 1))
                )
                self.current_struct.function_test_buf.append(
                    f"""for (int32_t ii = 0; ii < {test_length}; ii++) {{
                        g_assert_cmpint(lcm_msg->{field_name}[ii], ==, aspn->{field_name}[ii]);
                    }}"""
                )
                self.current_struct.function_free_buf.append(free)
            case "double" | "float":
                self.current_struct.function_from_prep_buf.append(
                    prep.format(
                        assign_rvalue=f"{random.uniform(0, 5)} * (ii + 1)"
                    )
                )
                self.current_struct.function_to_prep_buf.append(
                    c_prep.format(
                        assign_rvalue=f"{random.uniform(0, 5)} * (ii + 1)"
                    )
                )
                self.current_struct.function_test_buf.append(
                    f"""for (int32_t ii = 0; ii < {test_length}; ii++) {{
                        g_assert_cmpfloat(lcm_msg->{field_name}[ii], ==, aspn->{field_name}[ii]);
                    }}"""
                )
                self.current_struct.function_free_buf.append(free)
            case (
                "uint8_t"
                | "uint16_t"
                | "uint32_t"
                | "uint64_t"
                | "int8_t"
                | "int16_t"
                | "int32_t"
                | "int64_t"
            ):
                self.current_struct.function_from_prep_buf.append(
                    prep.format(
                        assign_rvalue=f"{random.randint(0, 5)} * (ii + 1)"
                    )
                )
                self.current_struct.function_to_prep_buf.append(
                    c_prep.format(
                        assign_rvalue=f"{random.randint(0, 5)} * (ii + 1)"
                    )
                )
                self.current_struct.function_test_buf.append(
                    f"""for (int32_t ii = 0; ii < {test_length}; ii++) {{
                        g_assert_cmpint(lcm_msg->{field_name}[ii], ==, aspn->{field_name}[ii]);
                    }}"""
                )
                self.current_struct.function_free_buf.append(free)
            case _:
                self.current_struct.function_from_prep_buf.append(
                    f"""lcm_msg{get}{field_name} = malloc({length} * sizeof({self.get_lcm_type_name(type_name)}));
                    for (int32_t ii = 0; ii < {length}; ii++) {{
                        lcm_msg{get}{field_name}[ii] = create_basic_{self.get_lcm_type_name(type_name)}();
                    }}"""
                )
                self.current_struct.function_to_prep_buf.append(
                    f"""aspn{get}{field_name} = malloc({c_length} * sizeof({self.remove_aspn_version(type_name)}));
                    for (int32_t ii = 0; ii < {c_length}; ii++) {{
                        aspn{get}{field_name}[ii] = create_basic_{self.remove_aspn_version(type_name)}();
                    }}"""
                )
                self.current_struct.function_test_buf.append(
                    f"""for (int32_t ii = 0; ii < {test_length}; ii++) {{
                        test_marshal_{type_name}(&lcm_msg->{field_name}[ii], &aspn->{field_name}[ii]);
                    }}"""
                )
                no_alloc_types = [
                    f"{ASPN_PREFIX}TypeIntegrity",
                    f"{ASPN_PREFIX}TypeSatnavSatelliteSystem",
                    f"{ASPN_PREFIX}TypeSatnavSignalDescriptor",
                    f"{ASPN_PREFIX}TypeHeader",
                    f"{ASPN_PREFIX}TypeKeplerOrbit",
                    f"{ASPN_PREFIX}TypeMounting",
                    f"{ASPN_PREFIX}TypeSatnavClock",
                    f"{ASPN_PREFIX}TypeSatnavTime",
                    f"{ASPN_PREFIX}TypeTimestamp",
                    f"{ASPN_PREFIX}TypeSatnavSvData",
                ]
                if type_name in no_alloc_types:
                    self.current_struct.function_free_buf.append(f"{free}")
                else:
                    self.current_struct.function_free_buf.append(
                        f"""for (int32_t ii = {test_length} - 1; ii >= 0; ii--) {{
                            free_basic_{self.get_lcm_type_name(type_name)}(&lcm_msg->{field_name}[ii]);
                        }}
                        {free}"""
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
        get = (
            "."
            if self.current_struct.struct_name.startswith("AspnType")
            else "->"
        )
        if type_name == "double":
            seed_val = 0.123
            seed_increment = 1.0035
            compare = "g_assert_cmpfloat"
        else:
            seed_val = 1
            seed_increment = 1
            compare = "g_assert_cmpint"
        if (
            (not isinstance(x, int))
            and field_name == "covariance"
            or field_name == "position_covariance"
            or field_name == "k"
        ):
            len_x = f"lcm_msg{get}{x}"
            len_y = f"lcm_msg{get}{y}"
            c_len_x = f"aspn{get}{x}"
            c_len_y = f"aspn{get}{y}"
            test_len_x = f"lcm_msg->{x}"
            test_len_y = f"lcm_msg->{y}"
            prep_loop = f"""lcm_msg{get}{field_name} = calloc({len_x}, sizeof({type_name}*));
            for (int32_t ii = 0; ii < {len_x}; ii++) {{
                lcm_msg{get}{field_name}[ii] = calloc({len_y}, sizeof({type_name}));
            }}
            {type_name} seed = {seed_val};
            for (int32_t ii = 0; ii < {len_x}; ii++) {{
                for (int32_t jj = 0; jj < {len_y}; jj++) {{
                    lcm_msg{get}{field_name}[ii][jj] = seed;
                    seed += {seed_increment};
                }}
            }}"""
            c_prep_loop = f"""aspn{get}{field_name} = calloc({c_len_x} * {c_len_y}, sizeof({type_name}));
            {type_name} seed = {seed_val};
            for (int32_t ii = 0, rr = 0; ii < {c_len_x}; ii++) {{
                for (int32_t jj = 0; jj < {c_len_y}; jj++) {{
                    aspn{get}{field_name}[ii + rr + jj] = seed;
                    seed += {seed_increment};
                }}
            }}"""
            test_loop = f"""for (int32_t ii = 0, rr = 0; ii < {test_len_x}; ii++) {{
                for (int32_t jj = 0; jj < {test_len_y}; jj++) {{
                    {compare}(lcm_msg->{field_name}[ii][jj], ==, aspn->{field_name}[ii + rr + jj]);
                }}
                rr += {test_len_x} - 1;
            }}"""
            free_loop = f"""for (int32_t ii = {test_len_x} - 1; ii >= 0; ii--) {{
                free(lcm_msg->{field_name}[ii]);
            }}
            free(lcm_msg->{field_name});"""
        else:
            len_x = x
            len_y = y
            c_len_x = x
            c_len_y = y
            test_len_x = x
            test_len_y = y
            prep_loop = f"""{type_name} seed = {seed_val};
            for (int32_t ii = 0; ii < {len_x}; ii++) {{
                for (int32_t jj = 0; jj < {len_y}; jj++) {{
                    lcm_msg{get}{field_name}[ii][jj] = seed;
                    seed += {seed_increment};
                }}
            }}"""
            c_prep_loop = f"""{type_name} seed = {seed_val};
            for (int32_t ii = 0; ii < {c_len_x}; ii++) {{
                for (int32_t jj = 0; jj < {c_len_y}; jj++) {{
                    aspn{get}{field_name}[ii][jj] = seed;
                    seed += {seed_increment};
                }}
            }}"""
            test_loop = f"""for (int32_t ii = 0; ii < {test_len_x}; ii++) {{
                for (int32_t jj = 0; jj < {test_len_y}; jj++) {{
                    {compare}(lcm_msg->{field_name}[ii][jj], ==, aspn->{field_name}[ii][jj]);
                }}
            }}"""
            free_loop = ""
        self.current_struct.function_from_prep_buf.append(prep_loop)
        self.current_struct.function_to_prep_buf.append(c_prep_loop)
        self.current_struct.function_test_buf.append(test_loop)
        self.current_struct.function_free_buf.append(free_loop)

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
        get = (
            "."
            if self.current_struct.struct_name.startswith("AspnType")
            else "->"
        )
        if field_type_name == f"{ASPN_PREFIX}MessageType":
            pass
        elif field_type_name == "char*":
            self.current_struct.function_from_prep_buf.append(
                f"""lcm_msg{get}{field_name} = malloc(7 * sizeof(char));
                memcpy(lcm_msg{get}{field_name}, \"abcdef\", 7);"""
            )
            self.current_struct.function_to_prep_buf.append(
                f"""aspn{get}{field_name} = malloc(7 * sizeof(char));
                memcpy(aspn{get}{field_name}, \"abcdef\", 7);"""
            )
            self.current_struct.function_test_buf.append(
                f"g_assert_cmpstr(lcm_msg->{field_name}, ==, aspn->{field_name});"
            )
            self.current_struct.function_free_buf.append(
                f"free(lcm_msg->{field_name});"
            )
        elif field_type_name == "bool":
            self.current_struct.function_from_prep_buf.append(
                f"lcm_msg{get}{field_name} = {random.randint(0, 1)};"
            )
            self.current_struct.function_to_prep_buf.append(
                f"aspn{get}{field_name} = {random.randint(0, 1)};"
            )
            self.current_struct.function_test_buf.append(
                f"g_assert_cmpint(lcm_msg->{field_name}, ==, aspn->{field_name});"
            )
        elif field_type_name in ["double", "float"]:
            self.current_struct.function_from_prep_buf.append(
                f"lcm_msg{get}{field_name} = {random.uniform(0, 5)};"
            )
            self.current_struct.function_to_prep_buf.append(
                f"aspn{get}{field_name} = {random.uniform(0, 5)};"
            )
            self.current_struct.function_test_buf.append(
                f"g_assert_cmpfloat(lcm_msg->{field_name}, ==, aspn->{field_name});"
            )
        elif field_type_name in [
            "uint8_t",
            "uint16_t",
            "uint32_t",
            "uint64_t",
            "int8_t",
            "int16_t",
            "int32_t",
            "int64_t",
        ]:
            self.current_struct.function_from_prep_buf.append(
                f"lcm_msg{get}{field_name} = {random.randint(1, 5)};"
            )
            self.current_struct.function_to_prep_buf.append(
                f"aspn{get}{field_name} = {random.randint(1, 5)};"
            )
            self.current_struct.function_test_buf.append(
                f"g_assert_cmpint(lcm_msg->{field_name}, ==, aspn->{field_name});"
            )
        else:
            no_alloc_types = [
                f"{ASPN_PREFIX}TypeIntegrity",
                f"{ASPN_PREFIX}TypeSatnavSatelliteSystem",
                f"{ASPN_PREFIX}TypeSatnavSignalDescriptor",
                f"{ASPN_PREFIX}TypeHeader",
                f"{ASPN_PREFIX}TypeKeplerOrbit",
                f"{ASPN_PREFIX}TypeMounting",
                f"{ASPN_PREFIX}TypeSatnavClock",
                f"{ASPN_PREFIX}TypeSatnavTime",
                f"{ASPN_PREFIX}TypeTimestamp",
                f"{ASPN_PREFIX}TypeSatnavSvData",
            ]
            self.current_struct.function_from_prep_buf.append(
                f"lcm_msg{get}{field_name} = create_basic_{self.get_lcm_type_name(field_type_name)}();"
            )
            if field_name == "observation_characteristics":
                self.current_struct.function_to_prep_buf.append(
                    f"""if (aspn{get}has_observation_characteristics) {{
                        aspn{get}{field_name} = create_basic_{self.remove_aspn_version(field_type_name)}();
                    }}"""
                )
                self.current_struct.function_test_buf.append(
                    f"""if (lcm_msg->has_observation_characteristics) {{
                        test_marshal_{field_type_name}(&lcm_msg->{field_name}, &aspn->{field_name});
                    }}"""
                )
            else:
                self.current_struct.function_to_prep_buf.append(
                    f"aspn{get}{field_name} = create_basic_{self.remove_aspn_version(field_type_name)}();"
                )
                self.current_struct.function_test_buf.append(
                    f"test_marshal_{field_type_name}(&lcm_msg->{field_name}, &aspn->{field_name});"
                )
            if field_type_name not in no_alloc_types:
                self.current_struct.function_free_buf.append(
                    f"free_basic_{self.get_lcm_type_name(field_type_name)}(&lcm_msg->{field_name});"
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
        get = (
            "."
            if self.current_struct.struct_name.startswith("AspnType")
            else "->"
        )
        enum = self.remove_aspn_version(
            enum_values[random.randint(0, len(enum_values) - 1)]
        ).split()[0]
        self.current_struct.function_from_prep_buf.append(
            f"lcm_msg{get}{field_name} = {enum};"
        )
        self.current_struct.function_to_prep_buf.append(
            f"aspn{get}{field_name} = {enum};"
        )
        self.current_struct.function_test_buf.append(
            f"g_assert_cmpint(lcm_msg->{field_name}, ==, aspn->{field_name});"
        )
