from os.path import join
from textwrap import dedent
from typing import Any, List, Union

from firehose.backends import Backend
from firehose.backends.aspn.utils import (
    ASPN_PREFIX,
    MatrixType,
    format_and_write_to_file,
    is_length_field,
    name_to_struct,
    pascal_to_snake,
)

EXTRA_CPP_INC = {
    'TypeTimestamp': """
#include <iomanip>
    """,
    'TypeSatnavTime': """
#include <limits>
#include <iostream>
    """,
}
EXTRA_CPP_DEF = {
    'TypeTimestamp': """
constexpr int NANO_PER_SEC = 1000000000;

TypeTimestamp to_type_timestamp(double time_in_sec) {
	return TypeTimestamp(static_cast<int64_t>(std::round(time_in_sec * NANO_PER_SEC)));
}

TypeTimestamp to_type_timestamp(int64_t sec, int64_t nsec) {
	return TypeTimestamp((sec * NANO_PER_SEC) + nsec);
}

double to_seconds(const TypeTimestamp& time) { return time.get_elapsed_nsec() * 1e-9; }

TypeTimestamp operator+(const TypeTimestamp& t1, const TypeTimestamp& t2) {
	return TypeTimestamp(t1.get_elapsed_nsec() + t2.get_elapsed_nsec());
}

TypeTimestamp operator+(const TypeTimestamp& t1, double t2_sec) {
	return t1 + to_type_timestamp(t2_sec);
}

TypeTimestamp operator+(double t1_sec, const TypeTimestamp& t2) {
	return to_type_timestamp(t1_sec) + t2;
}

TypeTimestamp operator-(const TypeTimestamp& t1, const TypeTimestamp& t2) {
	return TypeTimestamp(t1.get_elapsed_nsec() - t2.get_elapsed_nsec());
}

TypeTimestamp operator-(const TypeTimestamp& t1, double t2_sec) {
	return t1 - to_type_timestamp(t2_sec);
}

TypeTimestamp operator-(double t1_sec, const TypeTimestamp& t2) {
	return to_type_timestamp(t1_sec) - t2;
}

bool operator==(const TypeTimestamp& t1, const TypeTimestamp& t2) {
	return t1.get_elapsed_nsec() == t2.get_elapsed_nsec();
}

bool operator==(const TypeTimestamp& t1, double t2_sec) { return t1 == to_type_timestamp(t2_sec); }

bool operator==(double t1_sec, const TypeTimestamp& t2) { return to_type_timestamp(t1_sec) == t2; }

bool operator!=(const TypeTimestamp& t1, const TypeTimestamp& t2) {
	return t1.get_elapsed_nsec() != t2.get_elapsed_nsec();
}

bool operator!=(const TypeTimestamp& t1, double t2_sec) { return t1 != to_type_timestamp(t2_sec); }

bool operator!=(double t1_sec, const TypeTimestamp& t2) { return to_type_timestamp(t1_sec) != t2; }

bool operator<(const TypeTimestamp& t1, const TypeTimestamp& t2) {
	return t1.get_elapsed_nsec() < t2.get_elapsed_nsec();
}

bool operator<(const TypeTimestamp& t1, double t2_sec) { return t1 < to_type_timestamp(t2_sec); }

bool operator<(double t1_sec, const TypeTimestamp& t2) { return to_type_timestamp(t1_sec) < t2; }

bool operator>=(const TypeTimestamp& t1, const TypeTimestamp& t2) {
	return t1.get_elapsed_nsec() >= t2.get_elapsed_nsec();
}

bool operator>=(const TypeTimestamp& t1, double t2_sec) { return t1 >= to_type_timestamp(t2_sec); }

bool operator>=(double t1_sec, const TypeTimestamp& t2) { return to_type_timestamp(t1_sec) >= t2; }

bool operator>(const TypeTimestamp& t1, const TypeTimestamp& t2) {
	return t1.get_elapsed_nsec() > t2.get_elapsed_nsec();
}

bool operator>(const TypeTimestamp& t1, double t2_sec) { return t1 > to_type_timestamp(t2_sec); }

bool operator>(double t1_sec, const TypeTimestamp& t2) { return to_type_timestamp(t1_sec) > t2; }

bool operator<=(const TypeTimestamp& t1, const TypeTimestamp& t2) {
	return t1.get_elapsed_nsec() <= t2.get_elapsed_nsec();
}

bool operator<=(const TypeTimestamp& t1, double t2_sec) { return t1 <= to_type_timestamp(t2_sec); }

bool operator<=(double t1_sec, const TypeTimestamp& t2) { return to_type_timestamp(t1_sec) <= t2; }

std::ostream& operator<<(std::ostream& output, const TypeTimestamp& time) {
	int64_t nsec     = time.get_elapsed_nsec();
	int64_t sec      = nsec / NANO_PER_SEC;
	std::string sign = (nsec < 0) ? "-" : "";
	auto rounded_sec = nsec - (sec * NANO_PER_SEC);

    return output << sign << std::abs(sec) << '.' << std::setw(9) << std::setfill('0') << std::abs(rounded_sec) << "s";
}

""",
    'TypeSatnavTime': """

namespace {
constexpr double SECONDS_PER_WEEK = (60 * 60 * 24 * 7);

void compare_time_reference(const TypeSatnavTime& t1, const TypeSatnavTime& t2) {
	if (t1.get_time_reference() != t2.get_time_reference()) {
        std::cerr << "Cannot compare times. t1 has a time reference of "
        << t1.get_time_reference() << ", but t2 has a time reference of "
        << t2.get_time_reference() << std::endl;
	}
}

TypeSatnavTime correct_for_week_rollover(const TypeSatnavTime& t) {
	auto seconds = t.get_seconds_of_week();
	if (seconds > SECONDS_PER_WEEK || seconds < 0) {
		auto week_delta = std::floor(t.get_seconds_of_week() / SECONDS_PER_WEEK);
		auto new_week   = t.get_week_number() + week_delta;
		auto new_sec    = seconds - week_delta * SECONDS_PER_WEEK;
		// check for negative week number
		if (new_week < 0) {
			std::cerr << "Week number is " << new_week
            << " after correcting for rollover. " << std::endl;
		}
		return TypeSatnavTime(new_week, new_sec, t.get_time_reference());
	}
	return t;
}
}  // namespace

TypeSatnavTime operator+(const TypeSatnavTime& t, double t2_sec) {
	TypeSatnavTime t_out(
	    t.get_week_number(), t.get_seconds_of_week() + t2_sec, t.get_time_reference());
	return correct_for_week_rollover(t_out);
}

TypeSatnavTime operator-(const TypeSatnavTime& t, double t2_sec) { return t + -t2_sec; }

double operator-(const TypeSatnavTime& t1, const TypeSatnavTime& t2) {
	compare_time_reference(t1, t2);

	double dt = t1.get_seconds_of_week() - t2.get_seconds_of_week();
	dt += (t1.get_week_number() - t2.get_week_number()) * SECONDS_PER_WEEK;
	return dt;
}

bool operator==(const TypeSatnavTime& t1, const TypeSatnavTime& t2) {
	auto corr_t1 = correct_for_week_rollover(t1);
	auto corr_t2 = correct_for_week_rollover(t2);

	return corr_t1.get_time_reference() == corr_t2.get_time_reference() &&
	       corr_t1.get_week_number() == corr_t2.get_week_number() &&
	       std::fabs(corr_t1.get_seconds_of_week() - corr_t2.get_seconds_of_week()) <
	           std::numeric_limits<double>::epsilon();
}

bool operator!=(const TypeSatnavTime& t1, const TypeSatnavTime& t2) { return !(t1 == t2); }

bool operator>(const TypeSatnavTime& t1, const TypeSatnavTime& t2) {
	compare_time_reference(t1, t2);
	auto corr_t1 = correct_for_week_rollover(t1);
	auto corr_t2 = correct_for_week_rollover(t2);

	return corr_t1.get_week_number() > corr_t2.get_week_number() ||
	       (corr_t1.get_week_number() == corr_t2.get_week_number() &&
	        corr_t1.get_seconds_of_week() > corr_t2.get_seconds_of_week());
}

bool operator>=(const TypeSatnavTime& t1, const TypeSatnavTime& t2) {
	compare_time_reference(t1, t2);
	auto corr_t1 = correct_for_week_rollover(t1);
	auto corr_t2 = correct_for_week_rollover(t2);

	return corr_t1.get_week_number() > corr_t2.get_week_number() ||
	       (corr_t1.get_week_number() == corr_t2.get_week_number() &&
	        corr_t1.get_seconds_of_week() >= corr_t2.get_seconds_of_week());
}

bool operator<(const TypeSatnavTime& t1, const TypeSatnavTime& t2) { return !(t1 >= t2); }

bool operator<=(const TypeSatnavTime& t1, const TypeSatnavTime& t2) { return !(t1 > t2); }

std::ostream& operator<<(std::ostream& os, const TypeSatnavTime& t) {
	auto corr_t = correct_for_week_rollover(t);

	os << "[" << corr_t.get_week_number() << "] " << corr_t.get_seconds_of_week();
	return os;
}

""",
}


class Struct:
    def __init__(self, snake_case_struct_name: str, matrix_type_lower: str):
        self.struct_docstr: str = "<Missing C Docstring>"
        self.struct_name: str = name_to_struct(snake_case_struct_name)
        self.fn_basename: str = (
            f"{ASPN_PREFIX}_{snake_case_struct_name}".lower()
        )
        # All of the parameters (and their types) for the constructor that
        # accepts C++-style args.
        self.constructor_param_buf: List[str] = []

        # Maps parameters from the constructor that accepts C++-style args to
        # the ASPN-C _new() constructor.
        self.param_passthrough: List[str] = []

        # Gets parameters for the the ASPN-C _new() constructor from an
        # existing C++ class using the _get() methods. Used in the copy
        # constructor and copy assignment operator.
        self.param_getters: List[str] = []

        # Converts from a C++ array/matrix to a C-style array/matrix.
        self.param_prep: List[str] = []

        # Gets the C++ array/matrix (used by the above) via a _get() call.
        self.param_prep_prep: List[str] = []

        # Cleans up any memory allocated by param_prep
        self.param_prep_cleanup: List[str] = []

        # Implementation for all setters and getters for this class.
        self.setters_getters_buf: List[str] = []

        self.class_name = self.struct_name.removeprefix(ASPN_PREFIX)

        inheritance_param = ''
        inheritance_c_struct = ''
        inheritance_other = ''
        # inheritance_reset_header: Set parent's ASPN-C pointer to match the child's so it can be used polymorphically
        inheritance_reset_header = ''
        inheritance_overrides = f'''
        Aspn23MessageType {self.class_name}::get_message_type() const {{{{
            nullptr_check();
            auto c_header = ({ASPN_PREFIX}TypeHeader*)c_struct;
            return c_header->message_type;
        }}}}
        void {self.class_name}::set_message_type(Aspn23MessageType type) {{{{
            nullptr_check();
            auto c_header = ({ASPN_PREFIX}TypeHeader*)c_struct;
            c_header->message_type = type;
        }}}}

        uint32_t {self.class_name}::get_vendor_id() const {{{{
            nullptr_check();
            auto c_header = ({ASPN_PREFIX}TypeHeader*)c_struct;
            return c_header->vendor_id;

        }}}}
        void {self.class_name}::set_vendor_id(uint32_t id) {{{{
            nullptr_check();
            auto c_header = ({ASPN_PREFIX}TypeHeader*)c_struct;
            c_header->vendor_id = id;
        }}}}

        uint64_t {self.class_name}::get_device_id() const {{{{
            nullptr_check();
            auto c_header = ({ASPN_PREFIX}TypeHeader*)c_struct;
            return c_header->device_id;
        }}}}
        void {self.class_name}::set_device_id(uint64_t id) {{{{
            nullptr_check();
            auto c_header = ({ASPN_PREFIX}TypeHeader*)c_struct;
            c_header->device_id = id;
        }}}}

        uint32_t {self.class_name}::get_context_id() const {{{{
            nullptr_check();
            auto c_header = ({ASPN_PREFIX}TypeHeader*)c_struct;
            return c_header->context_id;

        }}}}
        void {self.class_name}::set_context_id(uint32_t id) {{{{
            nullptr_check();
            auto c_header = ({ASPN_PREFIX}TypeHeader*)c_struct;
            c_header->context_id = id;
        }}}}

        uint16_t {self.class_name}::get_sequence_id() const {{{{
            nullptr_check();
            auto c_header = ({ASPN_PREFIX}TypeHeader*)c_struct;
            return c_header->sequence_id;

        }}}}
        void {self.class_name}::set_sequence_id(uint16_t id) {{{{
            nullptr_check();
            auto c_header = ({ASPN_PREFIX}TypeHeader*)c_struct;
            c_header->sequence_id = id;
        }}}}
        '''
        if (
            self.class_name.startswith('Measurement')
            or self.class_name == 'Image'
        ):
            inheritance_param = ': TypeHeader(header)'
            inheritance_c_struct = 'TypeHeader(&c_struct->header, false),'
            inheritance_other = ': TypeHeader(&other.c_struct->header, false)'
            inheritance_reset_header = (
                'TypeHeader::reset_aspn_c(&this->c_struct->header, false);'
            )
        elif self.class_name.startswith('Metadata'):
            inheritance_param = ': TypeHeader(info.get_header())'
            inheritance_c_struct = 'TypeHeader(&c_struct->info.header, false),'
            inheritance_other = (
                ': TypeHeader(&other.c_struct->info.header, false)'
            )
            inheritance_reset_header = 'TypeHeader::reset_aspn_c(&this->c_struct->info.header, false);'
        else:
            inheritance_overrides = ''

        destructor = f'''{self.class_name}::~{self.class_name}() {{{{
            if (c_struct != nullptr && take_ownership)
                {self.fn_basename}_free(this->c_struct);
        }}}}'''

        self.source_template = dedent(f"""
            // This code is generated via firehose.
            // DO NOT hand edit code. Make any changes required using the firehose repo instead.

            #include "{self.struct_name[len(ASPN_PREFIX):]}.hpp"

            #include <stdexcept>
            {{extra_includes}}
            namespace {ASPN_PREFIX.lower()}_{matrix_type_lower} {{{{

            {self.class_name}::{self.class_name}({{constructor_params}}) {inheritance_param} {{{{
                {{constructor_param_prep}}
                this->c_struct = {self.fn_basename}_new({{constructor_param_names}});
                {{constructor_param_prep_cleanup}}
                this->take_ownership = true;

                {inheritance_reset_header}
            }}}}

            {self.class_name}::{self.class_name}({self.struct_name}* c_struct, bool take_ownership): {inheritance_c_struct} take_ownership(take_ownership) {{{{
                this->c_struct = c_struct;
            }}}}

            {self.class_name}::{self.class_name}(const {self.class_name}& other) {inheritance_other} {{{{
                {{constructor_param_prep_prep}}
                {{constructor_param_prep}}
                this->c_struct = {self.fn_basename}_new({{constructor_param_getters}});
                {{constructor_param_prep_cleanup}}
                this->take_ownership = true;

                {inheritance_reset_header}
            }}}}

            {self.class_name}& {self.class_name}::operator=(const {self.class_name}& other) {{{{
                // self-assignment check
                if (this != &other) {{{{
                    if (this->c_struct != nullptr && this->take_ownership)
                        {self.fn_basename}_free(this->c_struct);
                    {{constructor_param_prep_prep}}
                    {{constructor_param_prep}}
                    this->c_struct = {self.fn_basename}_new({{constructor_param_getters}});
                    {{constructor_param_prep_cleanup}}
                    this->take_ownership = true;

                    {inheritance_reset_header}
                }}}}
                return *this;
            }}}}

            {self.class_name}::{self.class_name}({self.class_name}&& other) {inheritance_other} {{{{
                this->c_struct = other.c_struct;
                other.c_struct = nullptr;
                this->take_ownership = other.take_ownership;
            }}}}

            {self.class_name}& {self.class_name}::operator=({self.class_name}&& rhs) {{{{
                // self-assignment check
                if (this != &rhs) {{{{
                    if (this->c_struct != nullptr && this->take_ownership)
                        {self.fn_basename}_free(this->c_struct);
                    this->c_struct = rhs.c_struct;
                    rhs.c_struct = nullptr;
                    this->take_ownership = rhs.take_ownership;
                }}}}
                return *this;
            }}}}

            {destructor}

            {inheritance_overrides}

            {self.struct_name}* {self.class_name}::get_aspn_c() const {{{{
                return c_struct;
            }}}}

            void {self.class_name}::reset_aspn_c({self.struct_name}* replacement_struct, bool take_ownership) {{{{
                if (this->c_struct != nullptr && this->take_ownership) {self.fn_basename}_free(this->c_struct);
                this->take_ownership = take_ownership;
                this->c_struct = replacement_struct;
            }}}}


            {{setters_getters}}

            void {self.class_name}::nullptr_check() const {{{{
                if (c_struct == nullptr)
                    throw std::runtime_error("{self.class_name} is holding a null pointer to ASPN-C data!");
            }}}}
            {{extra_definitions}}
            }}}}  // namespace {ASPN_PREFIX.lower()}_{matrix_type_lower}

        """)


class AspnYamlToCppSource(Backend):
    matrix_type: MatrixType = MatrixType.NONE
    current_struct: Struct = None
    structs: List[Struct] = []
    output_folder: str = None

    def __init__(self):
        self.current_struct: Struct = None
        self.structs: List[Struct] = []
        self.output_folder: str = None
        self.namespace = self.matrix_type.name.lower()
        self.directory = self.matrix_type.name.lower()

    def vector(self, type: str, size: Union[str, int]) -> str:
        pass

    def matrix(self, type: str, x: Union[str, int], y: Union[str, int]) -> str:
        pass

    def pointer_to_vector(
        self, pointer: str, length: Union[int, str], type: str
    ) -> str:
        pass

    def pointer_to_matrix(
        self, pointer: str, x: Union[int, str], y: Union[int, str], type: str
    ) -> str:
        pass

    def matrix_to_pointer(self) -> str:
        pass

    def length(self, field: str) -> str:
        pass

    def num_rows(self, field: str) -> str:
        pass

    def num_cols(self, field: str) -> str:
        pass

    def index_vector(self, x: str) -> str:
        pass

    def index_matrix(self, x: str, y: str, field_name) -> str:
        pass

    def set_output_root_folder(self, output_root_folder: str):
        self.output_folder = output_root_folder
        # Expecting parent AspnCppBackend to clear output folder

    def begin_struct(self, snake_case_struct_name):
        if self.current_struct is not None:
            self.structs += [self.current_struct]
        self.current_struct = Struct(snake_case_struct_name, self.namespace)

    def generate(self) -> str:
        # TODO- sort the struct params and "new" function params so they match and are in
        # an order that makes sense.
        self.structs += [self.current_struct]
        for struct in self.structs:
            c_file_contents = struct.source_template.format(
                constructor_params=', '.join(struct.constructor_param_buf),
                constructor_param_names=', '.join(struct.param_passthrough),
                constructor_param_getters=', '.join(struct.param_getters),
                constructor_param_prep=''.join(struct.param_prep),
                constructor_param_prep_prep=''.join(struct.param_prep_prep),
                constructor_param_prep_cleanup=''.join(
                    struct.param_prep_cleanup
                ),
                setters_getters=''.join(struct.setters_getters_buf),
                extra_includes=EXTRA_CPP_INC.get(struct.class_name, ''),
                extra_definitions=EXTRA_CPP_DEF.get(struct.class_name, ''),
            )

            basename = struct.struct_name.replace(f"{ASPN_PREFIX}", "")
            c_output_filename = join(self.output_folder, f"{basename}.cpp")
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

        # Use std::vector for ASPN types
        if type_name.startswith(ASPN_PREFIX):
            self.current_struct.param_prep_prep.append(
                f'auto {field_name} = other.get_{field_name}();'
            )
            self.current_struct.param_prep.append(f'''
                {type_name}* {field_name}_prep = new {type_name}[{field_name}.size()];
                for (size_t ii = 0; ii < {field_name}.size(); ii++) {{
                    auto c_object = {field_name}[ii].get_aspn_c();
                    {field_name}_prep[ii] = *c_object;
                }}
                ''')
            self.current_struct.param_prep_cleanup.append(f'''
                delete[] {field_name}_prep;
                ''')
            type_name = type_name[len(ASPN_PREFIX) :].strip("*")
            set_lengths = ''
            if isinstance(data_len, str):
                data_len = 'c_struct->' + data_len
                # Special case: the SatNav-with-SV-data measurement uses
                # one length field (num_signals_tracked) for multiple data
                # fields. In this case, length is already set.
                if not (
                    'num_signals_tracked' in data_len
                    and field_name == 'sv_data'
                ):
                    set_lengths = f'{data_len} = {field_name}.size();'
                    self.current_struct.param_getters.append(
                        f'other.get_{field_name}().size()'
                    )
                    self.current_struct.param_passthrough.append(
                        f'{field_name}.size()'
                    )
            fn_basename = pascal_to_snake(f_type)
            self.current_struct.setters_getters_buf.append(f"""
                std::vector<{type_name}> {self.current_struct.class_name}::get_{field_name}() const {{
                    nullptr_check();
                    if (c_struct->{field_name} == nullptr) return {{}};
                    std::vector<{type_name}> out;
                    for (size_t ii = 0; ii < {data_len}; ii++) {{
                        out.push_back({fn_basename}_copy(&c_struct->{field_name}[ii]));
                    }}
                    return out;
                }}

                void {self.current_struct.class_name}::set_{field_name}(std::vector<{type_name}> {field_name}) {{
                    nullptr_check();
                    for (size_t ii = 0; ii < {field_name}.size(); ii++) {{
                        auto c_object = {field_name}[ii].get_aspn_c();
                        c_struct->{field_name}[ii] = *c_object;
                    }}
                    {set_lengths}
                }}
            """)
            self.current_struct.constructor_param_buf.append(
                f'std::vector<{type_name}> {field_name}'
            )
            self.current_struct.param_passthrough.append(f'{field_name}_prep')
            self.current_struct.param_getters.append(f'{field_name}_prep')

        # Non-ASPN types
        else:
            set_lengths = ''
            ptr_field_check = ''
            get_ptr = ''
            shape = f'{data_len}'
            # Variable-length arrays
            if isinstance(data_len, str):
                get_ptr = f'c_struct->{field_name}'
                data_len = 'c_struct->' + data_len
                set_lengths = f'{data_len} = {self.length(field_name)};'
                # Special case: the time measurement uses one length field
                # (num_obs) for multiple data fields. In this case, length
                # is already set.
                if 'num_obs' in data_len and field_name in [
                    'elapsed_nsec',
                    'elapsed_attosec',
                ]:
                    pass
                # Special case: the magnetic field measurement uses one
                # length field (num_meas) for multiple data fields. In this
                # case, length is already set.
                elif 'num_meas' in data_len and field_name == 'b':
                    pass
                else:
                    self.current_struct.param_getters.append(
                        self.length(f'other.get_{field_name}()')
                    )
                    self.current_struct.param_passthrough.append(
                        f'{self.length(field_name)}'
                    )

                # All variable-length arrays
                self.current_struct.param_passthrough.append(
                    f'{field_name}.data()'
                )
                self.current_struct.param_getters.append(
                    f'other.get_{field_name}().data()'
                )
                ptr_field_check = (
                    f'if (c_struct->{field_name} == nullptr) return {{}};'
                )
            # Fixed-length arrays
            else:
                get_ptr = f'&c_struct->{field_name}[0]'
                self.current_struct.param_prep_prep.append(
                    f'auto {field_name} = other.get_{field_name}();'
                )
                self.current_struct.param_prep.append(f'''
                    {type_name} {field_name}_prep[{data_len}];
                    for (size_t ii = 0; ii < {data_len}; ii++)
                        {field_name}_prep[ii] = {field_name}{self.index_vector('ii')};
                    ''')
                self.current_struct.param_passthrough.append(
                    f'{field_name}_prep'
                )
                self.current_struct.param_getters.append(f'{field_name}_prep')
            self.current_struct.setters_getters_buf.append(f"""
                {self.vector(type_name, data_len)} {self.current_struct.class_name}::get_{field_name}() const {{
                    nullptr_check();
                    {ptr_field_check}
                    {self.pointer_to_vector(get_ptr, data_len, type_name)}
                }}

            void {self.current_struct.class_name}::set_{field_name}({self.vector(type_name, data_len)} {field_name}) {{
                nullptr_check();
                memcpy(c_struct->{field_name}, {field_name}.data(), {data_len} * sizeof({type_name}));
                {set_lengths}
            }}
            """)
            self.current_struct.constructor_param_buf.append(
                f'{self.vector(type_name, data_len)} {field_name}'
            )

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

        set_lengths = ''
        ptr_field_check = ''
        get_ptr = f'&c_struct->{field_name}[0][0]'
        if isinstance(x, str) and isinstance(y, str):
            x = 'c_struct->' + x
            y = 'c_struct->' + y

            # Special case: the time measurement uses one length field
            # (num_obs) for multiple data fields. In this case, length is
            # already set.
            # Special case: covariance length is already handled
            # by process_simple_field.
            if not ('num_obs' in x or field_name == 'covariance'):
                self.current_struct.param_getters.append(
                    self.num_cols(f'other.get_{field_name}()')
                )
                self.current_struct.param_passthrough.append(
                    f'{self.num_cols(field_name)}'
                )

            # Sometimes one size field is used twice. Make sure that isn't the
            # case here.
            if x != y:
                set_lengths = f'''
                    {x} = {self.num_rows(field_name)};
                    {y} = {self.num_cols(field_name)};
                '''
                self.current_struct.param_getters.append(
                    self.num_cols(f'other.get_{field_name}()')
                )
                self.current_struct.param_passthrough.append(
                    {self.num_cols(field_name)}
                )
            else:
                set_lengths = f'''
                    {x} = {self.num_cols(field_name)};
                '''

            ptr_field_check = (
                f'if (c_struct->{field_name} == nullptr) return {{}};'
            )
            get_ptr = f'c_struct->{field_name}'

            self.current_struct.param_passthrough.append(
                f'{field_name}{self.matrix_to_pointer()}'
            )
            self.current_struct.param_getters.append(
                f'other.get_{field_name}(){self.matrix_to_pointer()}'
            )
        elif isinstance(x, int) and isinstance(y, int):
            self.current_struct.param_prep_prep.append(
                f'auto {field_name} = other.get_{field_name}();'
            )
            self.current_struct.param_prep.append(f'''
                {type_name} {field_name}_prep[{x}][{y}];
                for (size_t row = 0; row < {x}; row++)
                    for (size_t col = 0; col < {y}; col++)
                        {field_name}_prep[row][col] = {field_name}{self.index_matrix('row', 'col', field_name)};
                ''')
            self.current_struct.param_passthrough.append(f'{field_name}_prep')
            self.current_struct.param_getters.append(f'{field_name}_prep')
        else:
            print(
                "Current implementation only supports homogeneous matrix size types."
            )
            print(
                "X and Y must BOTH be ints or BOTH be strings representing pointers)"
            )
            raise NotImplementedError

        self.current_struct.setters_getters_buf.append(f"""
            {self.matrix(type_name, x, y)} {self.current_struct.class_name}::get_{field_name}() const {{
                nullptr_check();
                {ptr_field_check}
                {self.pointer_to_matrix(get_ptr, x, y, type_name)}
            }}

        void {self.current_struct.class_name}::set_{field_name}({self.matrix(type_name, x, y)} {field_name}) {{
            nullptr_check();
            memcpy(c_struct->{field_name}, {field_name}{self.matrix_to_pointer()}, {x} * {y} * sizeof({type_name}));
            {set_lengths}
        }}
        """)

        field_str = f"{self.matrix(type_name, x, y)} {field_name}"
        self.current_struct.constructor_param_buf.append(field_str)

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
        self.current_struct.param_passthrough.append(
            f'const_cast<char*>({field_name}.c_str())'
        )
        self.current_struct.param_getters.append(
            f'const_cast<char*>(other.get_{field_name}().c_str())'
        )
        self.current_struct.setters_getters_buf.append(f"""
            std::string {self.current_struct.class_name}::get_{field_name}() const {{
                nullptr_check();
                return c_struct->{field_name};
            }}

            void {self.current_struct.class_name}::set_{field_name}(const std::string& {field_name}) {{
                nullptr_check();
                free(c_struct->{field_name});
                c_struct->{field_name} = strdup({field_name}.c_str());
            }}
            """)
        self.current_struct.constructor_param_buf.append(
            f"const std::string& {field_name}"
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
        if is_length_field(field_name):
            # Special case: metadata magnetic field has num_meas associated
            # with k and b.
            if (
                field_name == 'num_meas'
                and self.current_struct.class_name == 'MetadataMagneticField'
            ):
                pass
            # Special case: infer num_meas from size of
            # covariance.
            elif field_name == 'num_meas':
                self.current_struct.param_getters.append(
                    self.num_cols('other.get_covariance()')
                )
                self.current_struct.param_passthrough.append(
                    self.num_cols('covariance')
                )

            # Generate getters for length fields, but skip using them in constructors and don't
            # generate setters.
            self.current_struct.setters_getters_buf.append(f"""
                {field_type_name} {self.current_struct.class_name}::get_{field_name}() const {{
                    nullptr_check();
                    return c_struct->{field_name};
                }}
                """)
            return
        if field_type_name.startswith(f"{ASPN_PREFIX}Type"):
            self.current_struct.param_prep_prep.append(
                f'auto {field_name} = other.get_{field_name}();'
            )
            self.current_struct.param_prep.append(
                f'auto {field_name}_prep = {field_name}.get_aspn_c();'
            )
            function_basename = pascal_to_snake(field_type_name)
            self.current_struct.param_passthrough.append(f'{field_name}_prep')
            self.current_struct.param_getters.append(f'{field_name}_prep')
            field_type_name = field_type_name.removeprefix(ASPN_PREFIX)
            # Special case: fields called "observation_characteristics" have a companion field
            # called "has_observation_characteristics" that determines validity.
            if field_name == 'observation_characteristics':
                self.current_struct.setters_getters_buf.append(f"""
                    {field_type_name} {self.current_struct.class_name}::get_{field_name}() const {{
                        nullptr_check();
                        if (c_struct->has_observation_characteristics)
                            return {function_basename}_copy(&c_struct->{field_name});
                        return nullptr;
                    }}
                    """)
            else:
                self.current_struct.setters_getters_buf.append(f"""
                    {field_type_name} {self.current_struct.class_name}::get_{field_name}() const {{
                        nullptr_check();
                        return {function_basename}_copy(&c_struct->{field_name});
                    }}
                    """)
            self.current_struct.setters_getters_buf.append(f"""
                void {self.current_struct.class_name}::set_{field_name}({field_type_name} {field_name}) {{
                    nullptr_check();
                    auto c_object = std::move({field_name}).get_aspn_c();
                    c_struct->{field_name} = *c_object;
                }}
                """)
        else:
            self.current_struct.param_passthrough.append(field_name)
            self.current_struct.param_getters.append(
                f'other.get_{field_name}()'
            )
            self.current_struct.setters_getters_buf.append(f"""
                {field_type_name} {self.current_struct.class_name}::get_{field_name}() const {{
                    nullptr_check();
                    return c_struct->{field_name};
                }}

                void {self.current_struct.class_name}::set_{field_name}({field_type_name} {field_name}) {{
                    nullptr_check();
                    c_struct->{field_name} = {field_name};
                }}
                """)
        field_str = f"{field_type_name} {field_name}"
        self.current_struct.constructor_param_buf.append(field_str)

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
        field_str = f"{field_type_name} {field_name}"
        self.current_struct.constructor_param_buf.append(field_str)
        self.current_struct.param_passthrough.append(field_name)
        self.current_struct.param_getters.append(f'other.get_{field_name}()')
        self.current_struct.setters_getters_buf.append(f"""
            {field_type_name} {self.current_struct.class_name}::get_{field_name}() const {{
                nullptr_check();
                return c_struct->{field_name};
            }}

            void {self.current_struct.class_name}::set_{field_name}({field_type_name} {field_name}) {{
                nullptr_check();
                c_struct->{field_name} = {field_name};
            }}
            """)


class AspnYamlToXtensorSource(AspnYamlToCppSource):
    def __init__(self):
        self.matrix_type = MatrixType.XTENSOR
        super().__init__()

    def vector(self, type: str, size: Union[str, int]) -> str:
        if isinstance(size, int):
            return f'xt::xtensor_fixed<{type}, xt::xshape<{size}>>'
        else:
            return f'xt::xtensor<{type}, 1>'

    def matrix(self, type: str, x: Union[str, int], y: Union[str, int]) -> str:
        if isinstance(x, int) and isinstance(y, int):
            return f'xt::xtensor_fixed<{type}, xt::xshape<{x}, {y}>>'
        else:
            return f'xt::xtensor<{type}, 2>'

    def pointer_to_vector(
        self, pointer: str, length: Union[int, str], type: str
    ) -> str:
        return f'''std::vector<uint64_t> shape = {{{length}}};
                   return xt::adapt({pointer}, {length}, xt::no_ownership(), shape);'''

    def pointer_to_matrix(
        self, pointer: str, x: Union[int, str], y: Union[int, str], type: str
    ) -> str:
        data_len_adapt = ''
        if isinstance(x, str) and isinstance(y, str):
            data_len_adapt = f'{x} * {y}, xt::no_ownership(),'
        return f'''std::vector<std::size_t> shape = {{{x}, {y}}};
            return xt::adapt({pointer}, {data_len_adapt} shape);'''

    def matrix_to_pointer(self) -> str:
        return '.data()'

    def length(self, field: str) -> str:
        return f'{field}.size()'

    def num_rows(self, field: str) -> str:
        return f'{field}.dimension() == 1 ? {field}.shape()[0] : 0'

    def num_cols(self, field: str) -> str:
        return f'{field}.dimension() == 2 ? {field}.shape()[1] : 0'

    def index_vector(self, x: str) -> str:
        return f'({x})'

    def index_matrix(self, x: str, y: str, field: str) -> str:
        return f'({x}, {y})'


class AspnYamlToXtensorPySource(AspnYamlToXtensorSource):
    def __init__(self):
        super().__init__()
        self.directory = 'xtensor_py'

    def vector(self, type: str, _: Union[str, int]) -> str:
        return f'xt::pytensor<{type}, 1>'

    def matrix(
        self, type: str, _: Union[str, int], __: Union[str, int]
    ) -> str:
        return f'xt::pytensor<{type}, 2>'


class AspnYamlToEigenSource(AspnYamlToCppSource):
    def __init__(self):
        self.matrix_type = MatrixType.EIGEN
        super().__init__()

    def vector(self, type: str, _: Union[str, int]) -> str:
        return f'Eigen::Matrix<{type}, Eigen::Dynamic, 1>'

    def matrix(
        self, type: str, _: Union[str, int], __: Union[str, int]
    ) -> str:
        return f'Eigen::Matrix<{type}, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>'

    def pointer_to_vector(
        self, pointer: str, length: Union[int, str], type: str
    ) -> str:
        return f'return Eigen::Map<{self.vector(type, length)}>( {pointer}, {length});'

    def pointer_to_matrix(
        self, pointer: str, x: Union[int, str], y: Union[int, str], type: str
    ) -> str:
        return f'return Eigen::Map<{self.matrix(type, x, y)}>( {pointer}, {x}, {y});'

    def matrix_to_pointer(self) -> str:
        return '.data()'

    def length(self, field: str) -> str:
        return f'{field}.size()'

    def num_rows(self, field: str) -> str:
        return f'{field}.rows()'

    def num_cols(self, field: str) -> str:
        return f'{field}.cols()'

    def index_vector(self, x: str) -> str:
        return f'({x})'

    def index_matrix(self, x: str, y: str, field: str) -> str:
        return f'({x}, {y})'


class AspnYamlToStlSource(AspnYamlToCppSource):
    def __init__(self):
        self.matrix_type = MatrixType.STL
        super().__init__()

    def vector(self, type: str, _: Union[str, int]) -> str:
        return f'std::vector<{type}>'

    def matrix(
        self, type: str, _: Union[str, int], __: Union[str, int]
    ) -> str:
        return self.vector(type, '')

    def pointer_to_vector(
        self, pointer: str, length: Union[int, str], type: str
    ) -> str:
        return f'return {{{pointer}, {pointer} + {length}}};'

    def pointer_to_matrix(
        self, pointer: str, x: Union[int, str], y: Union[int, str], type: str
    ) -> str:
        return f'return {{{pointer}, {pointer} + {x} * {y}}};'

    def matrix_to_pointer(self) -> str:
        return '.data()'

    def length(self, field: str) -> str:
        return f'{field}.size()'

    def num_rows(self, field: str) -> str:
        return f'sqrt({field}.size())'

    def num_cols(self, field: str) -> str:
        return f'sqrt({field}.size())'

    def index_vector(self, x: str) -> str:
        return f'[{x}]'

    def index_matrix(self, x: str, y: str, field: str) -> str:
        return f'[{x} * {self.num_rows(field)} + {y}]'
