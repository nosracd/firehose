from os.path import join
from textwrap import dedent
from typing import List, Union
from typing import Any
from firehose.backends import Backend
from firehose.backends.aspn.utils import (
    ASPN_PREFIX,
    ASPN_PREFIX_LOWER,
    ASPN_NULLABLE_MACRO,
    format_and_write_to_file,
    name_to_struct,
    pascal_to_snake,
)


class Struct:
    def __init__(self, snake_case_struct_name: str):
        self.struct_docstr: str = "<Missing C Docstring>"
        self.struct_name: str = name_to_struct(snake_case_struct_name)
        self.fn_basename: str = (
            f"{ASPN_PREFIX_LOWER}_{snake_case_struct_name}".lower()
        )
        self.constructor_param_buf: List[str] = []
        self.new_call_prep: List[str] = []
        self.new_call_params: List[str] = []
        self.new_call_cleanup: List[str] = []
        self.constructor_body_buf: List[str] = [
            f"{self.struct_name}* self = (struct {self.struct_name}*)malloc(sizeof({self.struct_name}));"
            "if (NULL == self) return NULL;"
        ]
        self.free_pointer_fields_buf: List[str] = []
        self.header_template = dedent(f"""
            /*
             * This code is generated via firehose.
             * DO NOT hand edit code.  Make any changes required using the firehose repo instead
             */

            #include "{self.struct_name[len(ASPN_PREFIX):]}.h"

            {self.struct_name}* {ASPN_NULLABLE_MACRO} {self.fn_basename}_new({{constructor_params}}) {{{{
                {{constructor_body}}
                return self;
            }}}}

            {self.struct_name}* {ASPN_NULLABLE_MACRO} {self.fn_basename}_copy({self.struct_name}* input) {{{{
                {{new_call_prep}}
                {self.struct_name}* out = {self.fn_basename}_new({{new_call_params}});
                {{new_call_cleanup}}
                return out;
            }}}}

            void {self.fn_basename}_free(void* pointer) {{{{
                {self.struct_name}* self = ({self.struct_name}*)pointer;
                if (NULL == self) return;
                {self.fn_basename}_free_members(self);
                free(self);
            }}}}

            void {self.fn_basename}_free_members({self.struct_name}* self) {{{{
                if (NULL == self) return;
                {{free_pointer_fields}}
            }}}}
        """)

        self.free_ptr_field_template = dedent("""
            if (self->{field} != NULL) {{
                free(self->{field});
                self->{field} = NULL;
            }}
        """)


class AspnYamlToCSource(Backend):
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

    def _process_const_len_array_init(
        self,
        arr_name: str,
        arr_len: int,
        arr_type: str,
        nullable: bool = False,
    ):
        self.current_struct.constructor_body_buf.append(dedent(f"""
            if ({arr_name} != NULL)
                    memcpy(self->{arr_name}, {arr_name}, {arr_len} * sizeof({arr_type}));
            else
                for (size_t ii = 0; ii < {arr_len}; ii++) self->{arr_name}[ii] = NAN;
        """))

    def _process_array_ptr_init(
        self,
        arr_name: str,
        array_len_ptr_name: str,
        arr_type: str,
        nullable: bool = False,
    ):
        copy_array = f'self->{arr_name} = ({arr_type}*)calloc({array_len_ptr_name}, sizeof({arr_type}));'
        if arr_type.startswith(f"{ASPN_PREFIX}Type"):
            basename = pascal_to_snake(arr_type)
            copy_array = f'''
            {copy_array}
            for (size_t ii = 0; ii < {array_len_ptr_name}; ii++) {{
                {arr_type}* pointer = {basename}_copy(&{arr_name}[ii]);
                self->{arr_name}[ii] = *pointer;
                free(pointer);
            }}
            '''
            self.current_struct.free_pointer_fields_buf.append(f'''
                if (self->{arr_name} != NULL && self->{array_len_ptr_name} !=0) {{
                    for (size_t ii = 0; ii < self->{array_len_ptr_name}; ii++)
			            {basename}_free_members(&self->{arr_name}[ii]);
                    free(self->{arr_name});
                }}
                ''')
        else:
            self.current_struct.free_pointer_fields_buf.append(f'''
                if (self->{arr_name} != NULL && self->{array_len_ptr_name} !=0) {{
                    free(self->{arr_name});
                }}
                ''')
            copy_array = f'''
            {copy_array}
            memcpy(self->{arr_name}, {arr_name}, sizeof({arr_type}) * {array_len_ptr_name});
            '''
        self.current_struct.constructor_body_buf.append(dedent(f"""
            self->{arr_name} = NULL;
            if ({arr_name} != NULL && {array_len_ptr_name} !=0) {{
                if ({array_len_ptr_name} == 0) self->{arr_name} = NULL;
                else if ({array_len_ptr_name} > 0) {{
                    {copy_array}
                }} else {{
                    fprintf(stderr, "An error occurred: '%s' defines the length '%s' and must be a positive integer", "{array_len_ptr_name}", "{arr_name}");
                    {self.current_struct.fn_basename}_free(self);
                    return NULL;
                }}
            }}
        """))

    def _process_matrix_ptr_init(
        self,
        mat_name: str,
        mat_ptr_x: str,
        mat_ptr_y: str,
        arr_type: str,
        nullable: bool = False,
    ):
        self.current_struct.constructor_body_buf.insert(
            0, f'size_t {mat_name}_elements;'
        )
        self.current_struct.constructor_body_buf.append(dedent(f"""
            self->{mat_name} = NULL;
            if ({mat_name} != NULL && {mat_ptr_x} != 0 && {mat_ptr_y} != 0) {{
                {mat_name}_elements = {mat_ptr_x} * {mat_ptr_y};
                if ({mat_name}_elements > 0) {{
                    self->{mat_name} = ({arr_type}*)calloc({mat_name}_elements, sizeof({arr_type}));
                    memcpy(self->{mat_name}, {mat_name}, {mat_name}_elements * sizeof({arr_type}));
                }} else {{
                    fprintf(stderr, "An error occurred: (%s * %s) defines the row and column lengths of '%s' and both must be a positive integer", "{mat_ptr_x}", "{mat_ptr_y}", "{mat_name}");
                    {self.current_struct.fn_basename}_free(self);
                    return NULL;
                }}
            }}
        """))
        self.current_struct.free_pointer_fields_buf.append(
            f'free(self->{mat_name});'
        )

    def _process_const_size_matrix_init(
        self,
        mat_name: str,
        mat_len_x: int,
        mat_len_y: int,
        mat_type: str,
        nullable: bool = False,
    ):
        total_size = mat_len_x * mat_len_y
        if total_size <= 0:
            raise ValueError('X and Y must both be positive integers!')
        self.current_struct.constructor_body_buf.append(dedent(f"""
            if ({mat_name} != NULL)
                memcpy(self->{mat_name}, {mat_name}, {total_size} * sizeof({mat_type}));
            else
                for (size_t ii = 0; ii < {mat_len_x}; ii++)
                    for (size_t jj = 0; jj < {mat_len_y}; jj++)
                        self->{mat_name}[ii][jj] = NAN;
        """))

    def generate(self) -> str:
        # TODO- sort the struct params and "new" function params so they match and are in
        # an order that makes sense.
        self.structs += [self.current_struct]
        for struct in self.structs:
            c_file_contents = struct.header_template.format(
                constructor_body='\n'.join(struct.constructor_body_buf),
                constructor_params=', '.join(struct.constructor_param_buf),
                new_call_prep='\n'.join(struct.new_call_prep),
                new_call_params=', '.join(struct.new_call_params),
                new_call_cleanup='\n'.join(struct.new_call_cleanup),
                free_pointer_fields='\n'.join(struct.free_pointer_fields_buf),
            )

            basename = struct.struct_name.replace(f"{ASPN_PREFIX}", "")
            c_output_filename = join(self.output_folder, f"{basename}.c")
            format_and_write_to_file(c_file_contents, c_output_filename)

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # # # # # # # # # # # # # # # Backend Methods # # # # # # # # # # # # # # #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    def process_func_ptr_field_with_self(
        self,
        field_name: str,
        params: List[Any],
        return_t: Any,
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
        f_name = field_name
        f_type = type_name
        if isinstance(data_len, int):
            f_name += f"[{data_len}]"
            self._process_const_len_array_init(
                field_name, data_len, type_name, nullable
            )

        elif isinstance(data_len, str):
            f_type = f"{type_name}*"
            self._process_array_ptr_init(
                field_name, data_len, type_name, nullable
            )

        self.current_struct.constructor_param_buf.append(f"{f_type} {f_name}")
        self.current_struct.new_call_params.append(f"input->{field_name}")

    def process_matrix_field(
        self,
        field_name: str,
        type_name: str,
        x: Union[int, str],
        y: Union[int, str],
        doc_string: str,
        nullable: bool = False,
    ):
        try:
            x = int(x)
        except ValueError:
            pass
        try:
            y = int(y)
        except ValueError:
            pass
        field_str = f"{type_name} {field_name}[{x}][{y}]"
        if isinstance(x, int) and isinstance(y, int):
            self._process_const_size_matrix_init(field_name, x, y, type_name)
        elif isinstance(x, str) and isinstance(y, str):
            field_str = f"{type_name}* {field_name}"
            self._process_matrix_ptr_init(field_name, x, y, type_name)
        else:
            print(
                "Current implementation only supports homogeneous matrix size types."
            )
            print(
                "X and Y must BOTH be ints or BOTH be strings representing pointers)"
            )
            raise NotImplementedError

        self.current_struct.constructor_param_buf.append(field_str)
        self.current_struct.new_call_params.append(f"input->{field_name}")

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
        self.current_struct.new_call_params.append(f"input->{field_name}")
        self.current_struct.constructor_param_buf.append(f"char* {field_name}")
        self.current_struct.constructor_body_buf.append(
            f"""if ({field_name} == NULL) return NULL;
                size_t len = strlen({field_name}) + 1;
                self->{field_name} = malloc(len);
                memcpy(self->{field_name}, {field_name}, len);"""
        )
        self.current_struct.free_pointer_fields_buf.append(
            f'free(self->{field_name});'
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
        basename = pascal_to_snake(field_type_name)

        if f'{ASPN_PREFIX}Type' in field_type_name:
            self.current_struct.new_call_params.append(f"{field_name}_prep")
            self.current_struct.constructor_param_buf.append(
                f"{field_type_name}* {field_name}"
            )
            # Special case: fields called "observation_characteristics" have a companion field
            # called "has_observation_characteristics" that determines validity.
            if field_name == 'observation_characteristics':
                self.current_struct.constructor_body_buf.append(f"""
                    if (has_observation_characteristics) {{
                        {field_type_name}* {field_name}_prep = {basename}_copy({field_name});
                        self->{field_name} = *{field_name}_prep;
                        free({field_name}_prep);
                    }}
                    """)
                self.current_struct.new_call_prep.append(f'''
                    {field_type_name}* {field_name}_prep = NULL;
                    if (input->has_observation_characteristics)
                        {field_name}_prep = {basename}_copy(&input->{field_name});
                    ''')
                self.current_struct.new_call_cleanup.append(f'''
                    if (input->has_observation_characteristics)
                        {basename}_free({field_name}_prep);
                    ''')
                self.current_struct.free_pointer_fields_buf.append(f'''
                    if (self->has_observation_characteristics)
                        {basename}_free_members(&self->{field_name});
                    ''')
            # All other type classes.
            else:
                self.current_struct.constructor_body_buf.append(f"""
                    {field_type_name}* {field_name}_prep = {basename}_copy({field_name});
                    self->{field_name} = *{field_name}_prep;
                    free({field_name}_prep);
                    """)
                self.current_struct.new_call_prep.append(
                    f'{field_type_name}* {field_name}_prep = {basename}_copy(&input->{field_name});'
                )
                self.current_struct.new_call_cleanup.append(
                    f'{basename}_free({field_name}_prep);'
                )
                self.current_struct.free_pointer_fields_buf.append(
                    f'{basename}_free_members(&self->{field_name});'
                )
        else:
            self.current_struct.new_call_params.append(f"input->{field_name}")
            self.current_struct.constructor_param_buf.append(
                f"{field_type_name} {field_name}"
            )
            self.current_struct.constructor_body_buf.append(
                f"self->{field_name} = {field_name};"
            )

    def process_class_docstring(self, doc_string: str, nullable: bool = False):
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
        doc_str: str,
        enum_values_doc_strs: List[str],
        nullable: bool = False,
    ):
        param_name = field_name
        field_str = f"enum {field_type_name} {param_name}"

        self.current_struct.constructor_param_buf.append(field_str)
        self.current_struct.new_call_params.append(f"input->{param_name}")
        self.current_struct.constructor_body_buf.append(
            f"self->{field_name} = {param_name};"
        )
