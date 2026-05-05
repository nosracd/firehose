from glob import glob
from os import makedirs, remove
from os.path import join
from textwrap import dedent
from typing import List, Union
from ..backend import Backend
from .aspn_yaml_to_c_source import AspnYamlToCSource
from .aspn_yaml_to_c_header import AspnYamlToCHeader
from .utils import (
    ASPN_DISABLE_NULLABILITY,
    ASPN_NULLABILITY_MACRO_END,
    ASPN_NULLABILITY_MACRO_START,
    ASPN_NULLABLE_MACRO,
    ASPN_PREFIX,
    format_and_write_to_file,
    name_to_enum_value,
    snake_to_pascal,
)

ASPN_DIR = ASPN_PREFIX.lower()
ASPN_PREFIX_LOWER = ASPN_PREFIX.lower()


class AspnCBackend(Backend):
    def __init__(self):
        self.c_source_generator = AspnYamlToCSource()
        self.c_header_generator = AspnYamlToCHeader()
        self.all_types_enum = []
        self.all_source_files = []
        self.all_aliases = ''
        self.free_cases = ''
        self.type_string_cases = ''
        self.aspn_type_get_time_cases = ''
        self.aspn_type_set_time_cases = ''
        self.aspn_copy_message_cases = ''
        self.enums_in_current_struct = []
        self.messages_types_includes = ''

    def _remove_existing_output_files(self):
        for file in glob(f"{self.output_folder}/*.h"):
            remove(file)

        for file in glob(f"{self.output_folder}/*.c"):
            remove(file)

    def _generate_meson_build(self):
        print("Generating meson.build")
        meson_build_template = dedent(dedent(dedent("""
            # This code is generated via firehose.
            # DO NOT hand edit code. Make any changes required using the firehose repo instead.

            aspn_sources = [
            {sources}
            ]

            aspn_headers = [
            {headers}
            ]

            install_headers(aspn_headers, subdir: 'aspn23')

            aspn_c_inc_dir = include_directories('src')

            if not get_option('aspn-cpp-xtensor-py').disabled()
                # Used by python bindings module in ASPN-C++.
                aspn_c_static_lib_no_asan = static_library('aspn_no_asan',
                                        sources: aspn_sources,
                                        override_options: ['b_coverage=false',
                                                        'b_sanitize=none'],
                                        include_directories: aspn_c_inc_dir)

            aspn_c_no_asan_dep = declare_dependency(link_whole: aspn_c_static_lib_no_asan,
                                    include_directories: aspn_c_inc_dir)

            endif

            if get_option('aspn-c-main-library')

                aspn_c_libs = both_libraries('aspn',
                                        sources: aspn_sources,
                                        include_directories: aspn_c_inc_dir,
                                        soversion: meson.project_version(),
                                        install: true)

                aspn_c_dep = declare_dependency(link_with: aspn_c_libs.get_shared_lib(),
                                        include_directories: aspn_c_inc_dir)

                foreach source : aspn_sources
                    header = source.replace('.c', '.h')
                    install_headers(header, install_dir: get_option('includedir') + '/aspn23')
                endforeach
                install_headers('src/aspn23/aspn.h', install_dir: get_option('includedir') + '/aspn23')
                install_headers('src/aspn23/common.h', install_dir: get_option('includedir') + '/aspn23')
                install_headers('src/aspn23/messages_and_types.h', install_dir: get_option('includedir') + '/aspn23')

                aspn_runtime_types = [
                {types}
                ]

                pkg = import('pkgconfig')
                pkg.generate(aspn_c_libs,
                    name: 'aspn23',
                    description: 'ASPN c',
                    unescaped_variables: 'aspn_runtime_types=' + ' '.join(aspn_runtime_types),
                    version: meson.project_version())

                meson.override_dependency('aspn23', aspn_c_dep)

            else # get_option('aspn-c-main-library')

                aspn_c_dep = disabler()

            endif

        """)))

        types_meson = '    \'' + '\',\n    \''.join(self.all_types_enum) + '\''

        # Build out list of headers, starting with the sources but also adding in the headers
        # without a corresponding source.
        headers = [
            source.replace('.c', '.h') for source in self.all_source_files
        ]
        headers.insert(0, '    \'src/aspn23/messages_and_types.h\',')
        headers.insert(0, '    \'src/aspn23/common.h\',')
        headers.insert(0, '    \'src/aspn23/aspn.h\',')

        meson_build = meson_build_template.format(
            sources='\n'.join(self.all_source_files),
            headers='\n'.join(headers),
            types=types_meson,
            ASPN_DIR=ASPN_DIR,
        )
        meson_build_filename = self.output_folder.replace(
            f'/src/{ASPN_DIR}', '/meson.build'
        )
        with open(meson_build_filename, "w", encoding="utf-8") as f:
            f.write(meson_build)

    def _generate_unversioned_header(self):
        print("Generating aspn.h and aspn.c")
        aspn_h_template = f"""
            /*
            * This code is generated via firehose.
            * DO NOT hand edit code.  Make any changes required using the firehose repo instead.
            */

            #pragma once

            #ifdef __cplusplus
            extern "C" {{{{
            #endif

            #include "types.h"
            typedef enum Aspn23MessageType AspnMessageType;
            #define aspn_free {ASPN_PREFIX_LOWER}_free
            #define aspn_runtime_type_get_name {ASPN_PREFIX_LOWER}_runtime_type_get_name

            #include "utils.h"
            #define aspn_is_core_message {ASPN_PREFIX_LOWER}_is_core_message
            #define aspn_get_time {ASPN_PREFIX_LOWER}_get_time
            #define aspn_set_time {ASPN_PREFIX_LOWER}_set_time
            #define aspn_copy_message {ASPN_PREFIX_LOWER}_copy_message

            #include "messages_and_types.h"
            {{aliases}}

            #ifdef __cplusplus
            }}}}  // extern "C"
            #endif
        """

        header_contents = aspn_h_template.format(aliases=self.all_aliases)
        output_filepath = join(self.output_folder, "aspn.h")
        format_and_write_to_file(header_contents, output_filepath)

    def _generate_meta_header(self):
        print("Generating aspn.h and aspn.c")
        meta_template = """
            /*
            * This code is generated via firehose.
            * DO NOT hand edit code.  Make any changes required using the firehose repo instead.
            */

            #pragma once

            {includes}
        """

        header_contents = meta_template.format(
            includes=self.messages_types_includes
        )
        output_filepath = join(self.output_folder, "messages_and_types.h")
        format_and_write_to_file(header_contents, output_filepath)

    def _generate_utils(self):
        print("Generating utils.h and utils.c")
        utils_h = f"""
            /*
            * This code is generated via firehose.
            * DO NOT hand edit code.  Make any changes required using the firehose repo instead.
            */

            #pragma once

            #ifdef __cplusplus
            extern "C" {{
            #endif

            #include <{ASPN_PREFIX_LOWER}/TypeTimestamp.h>
            #include <{ASPN_PREFIX_LOWER}/TypeHeader.h>

            /*
            * An alias for cases where the object has been up-casted and should be
            * down-casted before using it.
            */
            typedef {ASPN_PREFIX}TypeHeader AspnBase;

            bool {ASPN_PREFIX_LOWER}_is_core_message(AspnBase* base);

            {ASPN_PREFIX}TypeTimestamp {ASPN_PREFIX_LOWER}_get_time(const AspnBase* base);
            void {ASPN_PREFIX_LOWER}_set_time(AspnBase* base, {ASPN_PREFIX}TypeTimestamp time);

            AspnBase* {ASPN_PREFIX_LOWER}_copy_message(AspnBase* base);

            #ifdef __cplusplus
            }}  // extern "C"
            #endif
        """

        utils_c_template = """
            /*
            * This code is generated via firehose.
            * DO NOT hand edit code.  Make any changes required using the firehose repo instead.
            */

            #include <{ASPN_PREFIX_LOWER}/utils.h>
            #include <{ASPN_PREFIX_LOWER}/messages_and_types.h>

            bool {ASPN_PREFIX_LOWER}_is_core_message(AspnBase* base) {{
                if (base == NULL) {{
                    printf("is_core_message received a NULL pointer\\n");
                    return false;
                }}
                return base->message_type <= ASPN_LAST_MESSAGE;
            }}

            {ASPN_PREFIX}TypeTimestamp {ASPN_PREFIX_LOWER}_get_time(const AspnBase* base) {{
                switch(base->message_type) {{
                {aspn_type_get_time_cases}
                default: {{
                    printf("{ASPN_PREFIX_LOWER}_get_time: cannot get time from message of type %i\\n", base->message_type);
                    Aspn23TypeTimestamp out = {{0}};
                    return out;
                }}
                }}
            }}

            void {ASPN_PREFIX_LOWER}_set_time(AspnBase* base, {ASPN_PREFIX}TypeTimestamp time) {{
                switch(base->message_type) {{
                {aspn_type_set_time_cases}
                default: {{
                    printf("{ASPN_PREFIX_LOWER}_set_time: cannot get time from message of type %i\\n", base->message_type);
                    return;
                }}
                }}
            }}

            AspnBase* {ASPN_PREFIX_LOWER}_copy_message(AspnBase* base) {{
                switch(base->message_type) {{
                {aspn_copy_message_cases}
                default: {{
                    return NULL;
                }}
                }}
            }}
        """

        self.all_source_files += [f'    \'src/{ASPN_DIR}/utils.c\',']

        output_filepath = join(self.output_folder, "utils.h")
        format_and_write_to_file(utils_h, output_filepath)

        source_contents = utils_c_template.format(
            ASPN_PREFIX=ASPN_PREFIX,
            ASPN_PREFIX_LOWER=ASPN_PREFIX_LOWER,
            aspn_type_get_time_cases=self.aspn_type_get_time_cases,
            aspn_type_set_time_cases=self.aspn_type_set_time_cases,
            aspn_copy_message_cases=self.aspn_copy_message_cases,
        )
        output_filepath = join(self.output_folder, "utils.c")
        format_and_write_to_file(source_contents, output_filepath)

    def _generate_types_header(self):
        print("Generating types.h")
        types_h_template = """
            #pragma once

            #ifdef __cplusplus
            extern "C" {{
            #endif

            /**
            * An enum containing the entire set of measurements and metadata in ASPN
            */
            typedef enum {ASPN_PREFIX}MessageType {{
            /* ASPN_UNDEFINED should never be used. Indicates that uninitialized memory is being used */
            ASPN_UNDEFINED,
            {types},
            ASPN_LAST_MESSAGE={last_type},
            /*
            The values between ASPN_EXTENDED_BEGIN and ASPN_EXTENDED_END are reserved for extensions to
            ASPN. ASPN users may use these values for implementation-specific messages. Users utilizing
            these values must ensure all implementations coordinate on the interpretation of these values.
            These values should also begin with "ASPN_EXTENDED_". The types associated with these additional
            enum values should begin with "AspnExtended". For example, a new enum value might be called
            ASPN_EXTENDED_COMPASS_RESET with a corresponding struct named AspnExtendedCompassReset.

            Any values before ASPN_EXTENDED_BEGIN are reserved for usage by future ASPN revisions. Users
            must not use any value between ASPN_LAST_MESSAGE and ASPN_EXTENDED_BEGIN until those values are
            specified by a future ASPN revision.
            */
            ASPN_EXTENDED_BEGIN = 0x2000,
            ASPN_EXTENDED_END = 0xFFFF,
            }} {ASPN_PREFIX}MessageType;

            #define ASPN_NUM_MESSAGES {num_messages}

            void {ASPN_PREFIX_LOWER}_free(void* pointer);

            char* {ASPN_PREFIX_LOWER}_runtime_type_get_name({ASPN_PREFIX}MessageType type);

            #ifdef __cplusplus
            }}
            #endif
        """

        types_c_template = """
            #include <{ASPN_PREFIX_LOWER}/aspn.h>
            #include "types.h"

            void {ASPN_PREFIX_LOWER}_free(void* pointer) {{
                {ASPN_PREFIX}TypeHeader* self = ({ASPN_PREFIX}TypeHeader*)pointer;
                if (NULL == self) return;

                switch(self->message_type) {{
                case ASPN_UNDEFINED:
                    break;
                {aspn_free_cases}
                default: {{
                    printf("{ASPN_PREFIX_LOWER}_free: cannot free message of type %i\\n", self->message_type);
                    break;
                }}
                }}
            }}

            char* {ASPN_PREFIX_LOWER}_runtime_type_get_name({ASPN_PREFIX}MessageType type) {{
                switch(type) {{
                case ASPN_UNDEFINED:
                    return "UNDEFINED";
                {aspn_type_string_cases}
                default: {{
                    printf("{ASPN_PREFIX_LOWER}_runtime_type_get_name: cannot get name from message of type %i\\n", type);
                    return NULL;
                }}
                }}
            }}
        """

        self.all_source_files += [f'    \'src/{ASPN_DIR}/types.c\',']

        header_contents = types_h_template.format(
            types=','.join(self.all_types_enum),
            last_type=self.all_types_enum[-1],
            ASPN_PREFIX=ASPN_PREFIX,
            ASPN_PREFIX_LOWER=ASPN_PREFIX_LOWER,
            num_messages=len(self.all_types_enum) + 1,
        )
        output_filepath = join(self.output_folder, "types.h")
        format_and_write_to_file(header_contents, output_filepath)

        source_contents = types_c_template.format(
            aspn_free_cases=self.free_cases,
            aspn_type_string_cases=self.type_string_cases,
            ASPN_PREFIX=ASPN_PREFIX,
            ASPN_PREFIX_LOWER=ASPN_PREFIX_LOWER,
        )
        output_filepath = join(self.output_folder, "types.c")
        format_and_write_to_file(source_contents, output_filepath)

    def _generate_common_header(self):
        print("Generating common.h")
        common_h = f"""
            /*
            * This code is generated via firehose.
            * DO NOT hand edit code.  Make any changes required using the firehose repo instead.
            */

            #pragma once
            #include <stddef.h>
            #include <stdlib.h>
            #include <string.h>
            #include <stdbool.h>
            #include <stdio.h>
            #include <math.h>

            #include "types.h"

            #ifdef ASPN_NO_STDINT

            typedef char int8_t;
            typedef short int int16_t;
            typedef int int32_t;
            typedef unsigned char uint8_t;
            typedef unsigned short uint16_t;
            typedef unsigned int uint32_t;

            #	ifdef ASPN_LONG_LONG
            typedef long long int64_t;
            typedef unsigned long long uint64_t;
            #	else
            typedef long int64_t;
            typedef unsigned long uint64_t;
            #	endif

            #else
            #	include <stdint.h>
            #endif

            #ifndef __cplusplus
            #	ifdef ASPN_NO_BOOL
            #		define false 0
            #		define true 1
            #		define bool int
            #	else
            #		include <stdbool.h>
            #	endif
            #endif

            #ifndef __has_feature
            #	define __has_feature(x) 0
            #endif

            /**
            * Define a set of pragmas and attributes to instrument code to define whether or
            * not pointers may be null. This feature attempts to gracefully disable itself
            * if the current compiler is unable to support static analysis of nullability.
            * However, if this automatic disabling fails, the user may define {ASPN_DISABLE_NULLABILITY}
            * to force nullability checks off. In this case, the burden is
            * still on the user to not set NULL to pointers defined as not NULL.
            */
            #if __has_feature(nullability) && defined(_Pragma) && !defined({ASPN_DISABLE_NULLABILITY})

            /**
            * Indicates that pointers should be assumed to be not NULL unless
            * they are explicitly marked with {ASPN_NULLABLE_MACRO}.
            *
            * All pointers in type and function definitions declared in the region between
            * {ASPN_NULLABILITY_MACRO_START} and {ASPN_NULLABILITY_MACRO_END} in a file are
            * by default not NULL-able. For example, consider the following code:
            *
            *  #include <{ASPN_DIR}/aspn.h>
            *
            *  // After this macro, all pointers are assumed to be not NULL-able unless
            *  // otherwise marked
            *  {ASPN_NULLABILITY_MACRO_START}
            *
            *  // This function takes a int pointer parameter that must not be null
            *  int foo(int* a) {{ ... }}
            *  // This function takes a int pointer parameter that may be null
            *  int bar(int* {ASPN_NULLABLE_MACRO} a) {{ ... }}
            *
            *  ...
            *
            *  // Invalid-- parameter a cannot be NULL
            *  foo(NULL);
            *  // OK-- Parameter explicitly marked as nullable
            *  bar(NULL);
            *
            *  {ASPN_NULLABILITY_MACRO_END}
            *
            * Users of types within a ASPN_ASSUME_NONNULL region must ensure that pointer fields and
            * arguments are not populated with a NULL value when passing them across ASPN API
            * boundaries. Pointers explicitly annotated with {ASPN_NULLABLE_MACRO} are still nullable,
            * even when within such a region.
            */
            #	define {ASPN_NULLABILITY_MACRO_START} _Pragma("clang assume_nonnull begin")

            /**
            * Ending a default not NULL region started by {ASPN_NULLABILITY_MACRO_START}. Definitions
            * after a {ASPN_NULLABILITY_MACRO_END} return to ambiguous nullability unless otherwise
            * explicitly marked. */
            #	define {ASPN_NULLABILITY_MACRO_END} _Pragma("clang assume_nonnull end")

            /**
            * Declare a pointer as NULL-able. This macro should follow the pointer asterisk for the
            * pointer that is being declared NULL. Thus, `int ** {ASPN_NULLABLE_MACRO} foo` declares a
            * NULL-able pointer to a non-NULL pointer to int. */
            #	define {ASPN_NULLABLE_MACRO} _Nullable

            #	pragma clang diagnostic ignored "-Wnullability-extension"

            /**
            * This is needed due to a seeming bug in clang. Even with assume_nonnull, the compiler still
            * throws warnings for missing nullability attributes */
            #	pragma clang diagnostic ignored "-Wnullability-completeness"

            #else

            /**
            * This macro does nothing. To enable compiler non-null checking, compile using a compiler
            * that has the "nullability" feature and do not define {ASPN_DISABLE_NULLABILITY}. */
            #	define {ASPN_NULLABILITY_MACRO_START}

            /**
            * This macro does nothing. To enable compiler non-null checking, compile using a compiler
            * that has the "nullability" feature and do not define {ASPN_DISABLE_NULLABILITY}. */
            #	define {ASPN_NULLABILITY_MACRO_END}

            /**
            * This macro does nothing. To enable compiler non-null checking, compile using a compiler
            * that has the "nullability" feature and do not define {ASPN_DISABLE_NULLABILITY}. */
            #	define {ASPN_NULLABLE_MACRO}

            #endif
        """

        output_filepath = join(self.output_folder, f"common.h")
        format_and_write_to_file(common_h, output_filepath)

    def enums_to_aliases(self, enums: List[str]) -> str:
        enums = list(set(enums))  # remove duplicates
        enums.sort()
        all_aliases = ''
        for enum in enums:
            version_agnostic_enum = enum.replace(ASPN_PREFIX, 'Aspn')
            all_aliases += f'typedef enum {enum} {version_agnostic_enum};\n'
        return all_aliases

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = join(output_root_folder, 'src', ASPN_DIR)
        makedirs(self.output_folder, exist_ok=True)
        self._remove_existing_output_files()

        self.c_source_generator.set_output_root_folder(self.output_folder)
        self.c_header_generator.set_output_root_folder(self.output_folder)

    def begin_struct(self, struct_name: str):
        self.all_aliases += self.enums_to_aliases(self.enums_in_current_struct)
        self.enums_in_current_struct = []

        self.struct_name = struct_name

        print(f"Generating ASPN-C for {self.struct_name}")

        self.c_source_generator.begin_struct(self.struct_name)
        self.c_header_generator.begin_struct(self.struct_name)

        filename = snake_to_pascal(struct_name)

        if (
            self.struct_name.startswith('measurement')
            or self.struct_name.startswith('metadata')
            or self.struct_name == 'image'
        ):
            current_type = 'ASPN_' + struct_name.upper()
            self.all_types_enum += [current_type]

            function_name = self.struct_name.lower()

            self.free_cases += f"""
            case {current_type}:
                {ASPN_PREFIX_LOWER}_{function_name}_free(pointer);
            break;
            """

            self.type_string_cases += f"""
            case {current_type}:
                return "{ASPN_PREFIX.upper()}_{self.struct_name.upper()}";
            """

            self.aspn_type_get_time_cases += f"""
            case {current_type}: {{
                {ASPN_PREFIX}{filename}* child = ({ASPN_PREFIX}{filename}*) base;
                return child->time_of_validity;
            }}
            """

            self.aspn_type_set_time_cases += f"""
            case {current_type}: {{
                {ASPN_PREFIX}{filename}* child = ({ASPN_PREFIX}{filename}*) base;
                child->time_of_validity = time;
                return;
            }}
            """

            self.aspn_copy_message_cases += f"""
            case {current_type}: {{
                {ASPN_PREFIX}{filename}* child = ({ASPN_PREFIX}{filename}*) base;
                return (AspnBase*){ASPN_PREFIX_LOWER}_{function_name}_copy(child);
            }}
            """

        self.all_source_files += [f'    \'src/{ASPN_DIR}/{filename}.c\',']

        function_name = self.struct_name.lower()

        self.messages_types_includes += f'#include <{ASPN_DIR}/{filename}.h>\n'

        self.all_aliases += f"""
                              typedef {ASPN_PREFIX}{filename} Aspn{filename};
                              #define aspn_{function_name}_new {ASPN_PREFIX_LOWER}_{function_name}_new
                              #define aspn_{function_name}_copy {ASPN_PREFIX_LOWER}_{function_name}_copy
                              #define aspn_{function_name}_free {ASPN_PREFIX_LOWER}_{function_name}_free
                              #define aspn_{function_name}_free_members {ASPN_PREFIX_LOWER}_{function_name}_free_members
                              """

    def process_func_ptr_field_with_self(
        self,
        field_name: str,
        params,
        return_t,
        doc_string: str,
        nullable: bool = False,
    ):
        self.c_source_generator.process_func_ptr_field_with_self(
            field_name, params, return_t, doc_string, nullable
        )
        self.c_header_generator.process_func_ptr_field_with_self(
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
        self.c_source_generator.process_data_pointer_field(
            field_name, type_name, data_len, doc_string, deref, nullable
        )
        self.c_header_generator.process_data_pointer_field(
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
        self.c_source_generator.process_matrix_field(
            field_name, type_name, x, y, doc_string, nullable
        )
        self.c_header_generator.process_matrix_field(
            field_name, type_name, x, y, doc_string, nullable
        )

    def process_outer_managed_pointer_field(
        self, field_name: str, field_type_name: str, doc_string: str
    ):
        self.c_source_generator.process_outer_managed_pointer_field(
            field_name, field_type_name, doc_string
        )
        self.c_header_generator.process_outer_managed_pointer_field(
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
        self.c_source_generator.process_outer_managed_pointer_array_field(
            field_name, field_type_name, data_len, doc_string, deref, nullable
        )
        self.c_header_generator.process_outer_managed_pointer_array_field(
            field_name, field_type_name, data_len, doc_string, deref, nullable
        )

    def process_string_field(
        self, field_name: str, doc_string: str, nullable: bool = False
    ):
        self.c_source_generator.process_string_field(
            field_name, doc_string, nullable
        )
        self.c_header_generator.process_string_field(
            field_name, doc_string, nullable
        )

    def process_string_array_field(
        self, field_name: str, doc_string: str, nullable: bool = False
    ):
        self.c_source_generator.process_string_array_field(
            field_name, doc_string, nullable
        )
        self.c_header_generator.process_string_array_field(
            field_name, doc_string, nullable
        )

    def process_simple_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        self.c_source_generator.process_simple_field(
            field_name, field_type_name, doc_string, nullable
        )
        self.c_header_generator.process_simple_field(
            field_name, field_type_name, doc_string, nullable
        )

    def process_class_docstring(self, doc_string: str, nullable: bool = False):
        self.c_source_generator.process_class_docstring(doc_string, nullable)
        self.c_header_generator.process_class_docstring(doc_string, nullable)

    def process_inheritance_field(
        self,
        field_name: str,
        field_type_name: str,
        doc_string: str,
        nullable: bool = False,
    ):
        self.c_source_generator.process_inheritance_field(
            field_name, field_type_name, doc_string, nullable
        )
        self.c_header_generator.process_inheritance_field(
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
        enum_name = name_to_enum_value(self, field_name)
        for value in enum_values:
            value = value.split(' ')[0]
            unversioned_value = value.replace(ASPN_PREFIX.upper(), 'ASPN')
            self.all_aliases += f'#define {unversioned_value} {value}\n'
        self.enums_in_current_struct += [enum_name]
        self.c_source_generator.process_enum(
            field_name,
            field_type_name,
            enum_values,
            doc_string,
            enum_values_doc_strs,
        )
        self.c_header_generator.process_enum(
            field_name,
            field_type_name,
            enum_values,
            doc_string,
            enum_values_doc_strs,
        )

    def generate(self):
        self.c_source_generator.generate()
        self.c_header_generator.generate()

        self.all_aliases += self.enums_to_aliases(self.enums_in_current_struct)
        self.enums_in_current_struct = []

        self._generate_common_header()
        self._generate_unversioned_header()
        self._generate_meta_header()
        self._generate_utils()
        self._generate_types_header()
        self._generate_meson_build()
