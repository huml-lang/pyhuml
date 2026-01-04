"""
pyhuml - A Python implementation of HUML (Human-Oriented Markup Language)

HUML is a machine-readable markup language with a focus on readability by humans.
It borrows YAML's visual appearance, but avoids its complexities and ambiguities.
"""

import re
import math
import json
from typing import Any, Dict, List, Union, Optional, IO
from io import StringIO
from dataclasses import dataclass


# Precompiled regular expressions
BARE_KEY_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]*$')
VERSION_RE = re.compile(r'^v\d+\.\d+\.\d+$')

# Constants for better readability
SUPPORTED_VERSION = "v0.2.0"
MULTILINE_INDENT = 2  # Indentation for multiline content

VALUE_KEYWORDS = {
    'true': True,
    'false': False,
    'null': None,
    'nan': float('nan'),
    'inf': float('inf')
}

class HUMLError(Exception):
    """Base exception for HUML parsing errors."""
    pass


class HUMLParseError(HUMLError):
    """Exception raised when parsing fails."""

    def __init__(self, message: str, line: int):
        super().__init__(f"line {line}: {message}")
        self.line = line


@dataclass
class Parser:
    """Parser holds the state of the parsing process."""
    data: str
    pos: int = 0
    line: int = 1

    def __post_init__(self):
        # Convert to UTF-8 if needed
        if isinstance(self.data, bytes):
            self.data = self.data.decode('utf-8')

    def error(self, msg: str) -> HUMLParseError:
        """Create a parse error with current line number."""
        return HUMLParseError(msg, self.line)

    def done(self) -> bool:
        """Check if we've reached end of input."""
        return self.pos >= len(self.data)

    def peek(self, offset: int = 0) -> Optional[str]:
        """Peek at character at current position + offset."""
        pos = self.pos + offset
        return self.data[pos] if 0 <= pos < len(self.data) else None

    def peek_string(self, s: str) -> bool:
        """Check if string s appears at current position."""
        return self.data[self.pos:self.pos + len(s)] == s

    def advance(self, n: int = 1):
        """Advance position by n characters."""
        self.pos += n

    def skip_spaces(self):
        """Skip space characters (not newlines)."""
        while not self.done() and self.data[self.pos] == ' ':
            self.pos += 1

    def get_indent(self) -> int:
        """Get indentation level of current line."""
        # Find line start
        start = self.pos
        while start > 0 and self.data[start - 1] != '\n':
            start -= 1

        # Count spaces from line start
        indent = 0
        while start + indent < len(self.data) and self.data[start + indent] == ' ':
            indent += 1
        return indent

    def consume_line(self) -> None:
        """Consume rest of line, validating no trailing spaces."""
        content_start = self.pos
        self.skip_spaces()

        if self.done() or self.data[self.pos] == '\n':
            # Check for trailing spaces on empty line
            if self.pos > content_start:
                raise self.error("trailing spaces are not allowed")
        elif self.data[self.pos] == '#':
            # Handle inline comment
            if self.pos == content_start and self.get_indent() != self.pos - self._line_start():
                raise self.error(
                    "a value must be separated from an inline comment by a space")

            self.pos += 1  # Consume '#'
            if not self.done() and self.data[self.pos] not in ' \n':
                raise self.error(
                    "comment hash '#' must be followed by a space")

            # Skip to end of line
            while not self.done() and self.data[self.pos] != '\n':
                self.pos += 1

            # Check for trailing spaces in comment
            if self.pos > 0 and self.data[self.pos - 1] == ' ':
                raise self.error("trailing spaces are not allowed")
        else:
            raise self.error("unexpected content at end of line")

        # Consume newline
        if not self.done() and self.data[self.pos] == '\n':
            self.pos += 1
            self.line += 1

    def _line_start(self) -> int:
        """Find the start position of current line."""
        start = self.pos
        while start > 0 and self.data[start - 1] != '\n':
            start -= 1
        return start

    def consume_line_raw(self) -> str:
        """Read rest of line without validation (for multiline strings)."""
        start = self.pos
        while not self.done() and self.data[self.pos] != '\n':
            self.pos += 1

        content = self.data[start:self.pos]
        if not self.done():
            self.pos += 1
            self.line += 1

        return content

    def skip_blank_lines(self) -> None:
        """Skip empty lines and comment-only lines."""
        while not self.done():
            line_start = self.pos
            self.skip_spaces()

            if self.done():
                if self.pos > line_start:
                    raise self.error("trailing spaces are not allowed")
                return

            if self.data[self.pos] not in '\n#':
                return

            # Check for trailing spaces on blank lines
            if self.data[self.pos] == '\n' and self.pos > line_start:
                raise self.error("trailing spaces are not allowed")

            # Reset and consume the line
            self.pos = line_start
            self.consume_line()

    def expect_single_space(self, context: str) -> None:
        """Ensure exactly one space at current position."""
        if self.done() or self.data[self.pos] != ' ':
            raise self.error(f"expected single space {context}")

        self.advance()
        if not self.done() and self.data[self.pos] == ' ':
            raise self.error(
                f"expected single space {context}, found multiple")

    def expect_comma(self) -> None:
        """Consume a comma with correct spacing."""
        self.skip_spaces()
        if self.done() or self.data[self.pos] != ',':
            raise self.error("expected a comma in inline collection")

        # No spaces allowed before comma
        if self.pos > 0 and self.data[self.pos - 1] == ' ':
            raise self.error("no spaces allowed before comma")

        self.advance()
        self.expect_single_space("after comma")


def loads(data: Union[str, bytes]) -> Any:
    """
    Parse HUML data and return the corresponding Python object.

    Args:
        data: HUML formatted string or bytes

    Returns:
        Parsed Python object (dict, list, str, int, float, bool, or None)

    Raises:
        HUMLParseError: If the input is not valid HUML
    """
    if not data:
        raise HUMLError("empty document is undefined")

    parser = Parser(data)
    return _parse_document(parser)


def dumps(obj: Any, *, indent: int = 0) -> str:
    """
    Serialize a Python object to HUML format.

    Args:
        obj: Python object to serialize
        indent: Initial indentation level (internal use)

    Returns:
        HUML formatted string

    Raises:
        HUMLError: If the object cannot be serialized to HUML
    """
    output = StringIO()

    # Write version directive at document root
    if indent == 0:
        output.write(f"%HUML {SUPPORTED_VERSION}\n")

    _write_value(output, obj, indent)

    # Ensure document ends with newline
    result = output.getvalue()
    if result and not result.endswith('\n'):
        result += '\n'

    return result


def _parse_document(p: Parser) -> Any:
    """Parse the top-level HUML document."""
    # Check for version directive
    if p.peek_string("%HUML"):
        p.advance(5)

        # Parse optional version
        if not p.done() and p.data[p.pos] == ' ':
            p.advance()

            # Extract version string
            start = p.pos
            while not p.done() and p.data[p.pos] not in ' \n#':
                p.pos += 1

            if p.pos > start:
                version = p.data[start:p.pos]
                if version != SUPPORTED_VERSION:
                    raise p.error(
                        f"unsupported version '{version}'. expected '{SUPPORTED_VERSION}'")

        p.consume_line()

    p.skip_blank_lines()

    if p.done():
        raise p.error("empty document is undefined")

    # Root element must not be indented
    if p.get_indent() != 0:
        raise p.error("root element must not be indented")

    # Parse based on document type
    doc_type = _determine_doc_type(p)
    result = _parse_by_type(p, doc_type, 0)

    # Ensure no content follows root element
    p.skip_blank_lines()
    if not p.done():
        raise p.error(f"unexpected content after root {doc_type}")

    return result


def _determine_doc_type(p: Parser) -> str:
    """Determine the type of the root document."""
    # Check for forbidden root indicators first
    if p.peek_string("::"):
        raise p.error("'::' indicator not allowed at document root")
    if p.peek_string(":") and not _is_key_value_line(p):
        raise p.error("':' indicator not allowed at document root")

    # Check document patterns
    if _is_key_value_line(p):
        return 'inline_dict' if _is_inline_dict_root(p) else 'multiline_dict'

    if p.peek_string("[]"):
        return 'empty_list'
    if p.peek_string("{}"):
        return 'empty_dict'
    if p.peek() == '-':
        return 'multiline_list'
    if _has_comma_on_line(p):
        return 'inline_list'

    return 'scalar'


def _parse_by_type(p: Parser, doc_type: str, indent: int) -> Any:
    """Parse content based on determined type."""
    if doc_type == 'empty_list':
        p.advance(2)
        p.consume_line()
        return []

    elif doc_type == 'empty_dict':
        p.advance(2)
        p.consume_line()
        return {}

    elif doc_type == 'inline_dict':
        return _parse_inline_dict(p)

    elif doc_type == 'inline_list':
        return _parse_inline_list(p)

    elif doc_type == 'multiline_dict':
        return _parse_multiline_dict(p, indent)

    elif doc_type == 'multiline_list':
        return _parse_multiline_list(p, indent)

    elif doc_type == 'scalar':
        result = _parse_value(p, indent)
        p.consume_line()
        return result

    else:
        raise p.error(f"internal error: unknown type '{doc_type}'")


def _is_key_value_line(p: Parser) -> bool:
    """Check if current line has a key: value pattern."""
    saved_pos = p.pos
    try:
        _parse_key(p)
        return not p.done() and p.data[p.pos] == ':'
    except:
        return False
    finally:
        p.pos = saved_pos


def _is_inline_dict_root(p: Parser) -> bool:
    """Check if root is an inline dict (has both : and , on first line, nothing after)."""
    # Scan current line for patterns
    pos = p.pos
    has_colon = has_comma = has_double_colon = False

    while pos < len(p.data) and p.data[pos] not in '\n#':
        if p.data[pos] == ':':
            if pos + 1 < len(p.data) and p.data[pos + 1] == ':':
                has_double_colon = True
            has_colon = True
        elif p.data[pos] == ',':
            has_comma = True
        pos += 1

    if not (has_colon and has_comma and not has_double_colon):
        return False

    # Check if there's content after this line
    # Skip to next line
    while pos < len(p.data) and p.data[pos] != '\n':
        pos += 1
    if pos < len(p.data):
        pos += 1

    # Skip blank lines and comments to see if there's more content
    while pos < len(p.data):
        # Skip spaces
        while pos < len(p.data) and p.data[pos] == ' ':
            pos += 1

        if pos >= len(p.data):
            break

        # Blank line
        if p.data[pos] == '\n':
            pos += 1
            continue

        # Comment line
        if p.data[pos] == '#':
            while pos < len(p.data) and p.data[pos] != '\n':
                pos += 1
            if pos < len(p.data):
                pos += 1
            continue

        # Found non-blank, non-comment content
        return False

    return True


def _has_comma_on_line(p: Parser) -> bool:
    """Check if current line contains a comma (but no colon)."""
    pos = p.pos
    while pos < len(p.data) and p.data[pos] not in '\n#':
        if p.data[pos] == ',':
            return True
        if p.data[pos] == ':':
            return False
        pos += 1
    return False


def _parse_multiline_dict(p: Parser, indent: int) -> Dict[str, Any]:
    """Parse a multiline dictionary."""
    result = {}

    while True:
        p.skip_blank_lines()
        if p.done() or p.get_indent() < indent:
            break

        if p.get_indent() != indent:
            raise p.error(f"bad indent {p.get_indent()}, expected {indent}")

        # Parse key
        key = _parse_key(p)
        if key in result:
            raise p.error(f"duplicate key '{key}' in dict")

        # Parse indicator (: or ::)
        if not p.done() and p.data[p.pos] == ':':
            p.advance()
            if not p.done() and p.data[p.pos] == ':':
                # :: indicator - parse vector
                p.advance()
                result[key] = _parse_vector(p, indent + MULTILINE_INDENT)
            else:
                # : indicator - parse value
                p.expect_single_space("after ':'")

                # Check if multiline string
                is_multiline = p.peek_string('"""')
                result[key] = _parse_value(p, indent)

                if not is_multiline:
                    p.consume_line()
        else:
            raise p.error("expected ':' or '::' after key")

    return result


def _parse_multiline_list(p: Parser, indent: int) -> List[Any]:
    """Parse a multiline list."""
    result = []

    while True:
        p.skip_blank_lines()
        if p.done() or p.get_indent() < indent:
            break

        if p.get_indent() != indent:
            raise p.error(f"bad indent {p.get_indent()}, expected {indent}")

        if p.data[p.pos] != '-':
            break

        p.advance()
        p.expect_single_space("after '-'")

        # Check for nested vector
        if p.peek_string("::"):
            p.advance(2)
            value = _parse_vector(p, indent + MULTILINE_INDENT)
        else:
            value = _parse_value(p, indent)
            p.consume_line()

        result.append(value)

    return result


def _parse_vector(p: Parser, indent: int) -> Union[List, Dict]:
    """Parse a vector (list or dict) after :: indicator."""
    start_pos = p.pos
    p.skip_spaces()

    # Check for multiline vector
    if p.done() or p.data[p.pos] in '\n#':
        p.pos = start_pos
        # Capture line number of the vector indicator before skipping ahead
        vector_line = p.line
        p.consume_line()

        # Peek at next line to determine type
        p.skip_blank_lines()

        if p.done() or p.get_indent() < indent:
            raise HUMLParseError("ambiguous empty vector after '::'. Use [] or {}.", vector_line)

        # Determine type by first character
        return (
            _parse_multiline_list(p, indent)
            if p.data[p.pos] == "-"
            else _parse_multiline_dict(p, indent)
        )

    # Inline vector - must have exactly one space
    p.pos = start_pos
    p.expect_single_space("after '::'")

    # Check for empty markers
    if p.peek_string("[]"):
        p.advance(2)
        p.consume_line()
        return []

    if p.peek_string("{}"):
        p.advance(2)
        p.consume_line()
        return {}

    # Determine if dict or list by scanning for colons
    return _parse_inline_dict(p) if _has_dict_pattern(p) else _parse_inline_list(p)


def _has_dict_pattern(p: Parser) -> bool:
    """Check if inline collection has dict pattern (contains : but not ::)."""
    pos = p.pos
    while pos < len(p.data) and p.data[pos] not in '\n#':
        if p.data[pos] == ':' and (pos + 1 >= len(p.data) or p.data[pos + 1] != ':'):
            return True
        pos += 1
    return False


def _parse_inline_dict(p: Parser) -> Dict[str, Any]:
    """Parse inline dictionary contents."""
    result = {}
    is_first = True

    while not p.done() and p.data[p.pos] not in '\n#':
        if not is_first:
            p.expect_comma()
        is_first = False

        key = _parse_key(p)
        if key in result:
            raise p.error(f"duplicate key '{key}' in dict")

        if p.done() or p.data[p.pos] != ':':
            raise p.error("expected ':' in inline dict")

        p.advance()
        p.expect_single_space("in inline dict")

        value = _parse_value(p, 0)
        result[key] = value

        # Skip trailing spaces only if comma follows
        _skip_spaces_before_comma(p)

    p.consume_line()
    return result


def _parse_inline_list(p: Parser) -> List[Any]:
    """Parse inline list contents."""
    result = []
    is_first = True

    while not p.done() and p.data[p.pos] not in '\n#':
        if not is_first:
            p.expect_comma()
        is_first = False

        result.append(_parse_value(p, 0))

        # Skip trailing spaces only if comma follows
        _skip_spaces_before_comma(p)

    p.consume_line()
    return result


def _skip_spaces_before_comma(p: Parser) -> None:
    """Skip spaces only if followed by comma."""
    if not p.done() and p.data[p.pos] == ' ':
        # Peek ahead for comma
        next_pos = p.pos + 1
        while next_pos < len(p.data) and p.data[next_pos] == ' ':
            next_pos += 1
        if next_pos < len(p.data) and p.data[next_pos] == ',':
            p.skip_spaces()


def _parse_key(p: Parser) -> str:
    """Parse a dictionary key."""
    p.skip_spaces()

    if p.peek() == '"':
        return _parse_string(p)

    # Bare key - must start with letter
    if not p.peek() or not p.peek().isalpha():
        raise p.error("expected a key")

    start = p.pos
    while not p.done() and (p.data[p.pos].isalnum() or p.data[p.pos] in '-_'):
        p.pos += 1

    return p.data[start:p.pos]


def _parse_value(p: Parser, key_indent: int) -> Any:
    """Parse any scalar value."""
    if p.done():
        raise p.error("unexpected end of input, expected a value")

    c = p.data[p.pos]

    # String literals
    if c == '"':
        return _parse_multiline_string(p, key_indent) if p.peek_string('"""') else _parse_string(p)

    for keyword, value in VALUE_KEYWORDS.items():
        if p.peek_string(keyword):
            # Check that it's a complete word (not followed by alphanumeric or underscore)
            next_pos = p.pos + len(keyword)
            if next_pos >= len(p.data) or p.data[next_pos] not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_':
                p.advance(len(keyword))
                return value

    # Special numeric values with signs
    if c in '+-':
        p.advance()
        if p.peek_string('inf'):
            p.advance(3)
            return float('inf') if c == '+' else float('-inf')
        if _is_digit(p.peek()):
            p.pos -= 1  # Put sign back for number parser
            return _parse_number(p)
        raise p.error(f"invalid character after '{c}'")

    # Regular numbers
    if _is_digit(c):
        return _parse_number(p)

    raise p.error(f"unexpected character '{c}' when parsing value")


def _parse_string(p: Parser) -> str:
    """Parse a quoted string."""
    p.advance()  # Skip opening quote

    result = []
    escape_map = {
        '"': '"', '\\': '\\', '/': '/', 'n': '\n',
        't': '\t', 'r': '\r', 'b': '\b', 'f': '\f'
    }

    while not p.done():
        c = p.data[p.pos]

        if c == '"':
            p.advance()
            return ''.join(result)

        if c == '\n':
            raise p.error("newlines not allowed in single-line strings")

        if c == '\\':
            p.advance()
            if p.done():
                raise p.error("incomplete escape sequence")

            esc = p.data[p.pos]
            if esc in escape_map:
                result.append(escape_map[esc])
            else:
                raise p.error(f"invalid escape character '\\{esc}'")
        else:
            result.append(c)

        p.advance()

    raise p.error("unclosed string")


def _parse_multiline_string(p: Parser, key_indent: int) -> str:
    """Parse \"\"\" (preserves preceding space) multiline strings."""
    delim = p.data[p.pos:p.pos + 3]
    p.advance(3)
    p.consume_line()

    lines = []

    while not p.done():
        line_start = p.pos

        # Count indentation
        indent = 0
        while p.pos < len(p.data) and p.data[p.pos] == ' ':
            indent += 1
            p.pos += 1

        # Check for closing delimiter
        if p.peek_string(delim):
            if indent != key_indent:
                raise p.error(
                    f"multiline closing delimiter must be at same indentation as the key ({key_indent} spaces)")

            p.advance(3)
            p.consume_line()
            return '\n'.join(lines)

        # Get line content
        p.pos = line_start
        line_content = p.consume_line_raw()

        # Strip the required 2-space indent relative to the key
        req_indent = key_indent + MULTILINE_INDENT
        if len(line_content) >= req_indent and line_content[:req_indent].strip() == '':
            lines.append(line_content[req_indent:])
        else:
            lines.append(line_content)

    raise p.error("unclosed multiline string")


def _parse_number(p: Parser) -> Union[int, float]:
    """Parse numeric value."""
    start = p.pos

    # Handle sign
    if p.peek() in '+-':
        p.advance()

    # Check for special bases
    base_prefixes = {'0x': 16, '0o': 8, '0b': 2}
    for prefix, base in base_prefixes.items():
        if p.peek_string(prefix):
            return _parse_base_number(p, start, base, prefix)

    # Parse decimal number
    is_float = False

    while not p.done():
        c = p.data[p.pos]

        if c in '0123456789_':
            p.advance()
        elif c == '.':
            is_float = True
            p.advance()
        elif c in 'eE':
            is_float = True
            p.advance()
            if p.peek() in '+-':
                p.advance()
        else:
            break

    # Convert string to number
    num_str = p.data[start:p.pos].replace('_', '')

    try:
        if is_float:
            result = float(num_str)
            # Convert to int if it represents an integer value
            if result.is_integer():
                # For scientific notation, only convert if it's reasonable size and positive exponent
                if 'e' in num_str.lower():
                    # Parse the exponent
                    parts = num_str.lower().split('e')
                    if len(parts) == 2:
                        try:
                            exponent = int(parts[1])
                            # Only convert if positive exponent and result is reasonable size
                            if exponent >= 0 and abs(result) < 1e15:
                                return int(result)
                        except ValueError:
                            pass
                    return result
                else:
                    # Simple decimal like 0.0, 42.0 -> convert to int
                    return int(result)
            return result
        else:
            return int(num_str)
    except ValueError as e:
        raise p.error(f"invalid number: {e}")


def _parse_base_number(p: Parser, start: int, base: int, prefix: str) -> int:
    """Parse number in specific base."""
    p.advance(len(prefix))
    num_start = p.pos

    # Define valid digits for each base
    valid_chars = {
        2: '01',
        8: '01234567',
        16: '0123456789abcdefABCDEF'
    }

    while not p.done() and p.data[p.pos] in valid_chars[base] + '_':
        p.advance()

    if p.pos == num_start:
        raise p.error("invalid number literal, requires digits after prefix")

    # Handle sign
    sign = -1 if p.data[start] == '-' else 1

    # Parse number
    num_str = p.data[num_start:p.pos].replace('_', '')
    try:
        return sign * int(num_str, base)
    except ValueError as e:
        raise p.error(f"invalid number: {e}")


def _is_digit(c: Optional[str]) -> bool:
    """Check if character is a digit."""
    return c is not None and c.isdigit()


# Writing functions
def _write_value(output: IO[str], value: Any, indent: int) -> None:
    """Write a value to output in HUML format."""
    if value is None:
        output.write("null")
    elif isinstance(value, bool):
        output.write("true" if value else "false")
    elif isinstance(value, (int, float)):
        _write_number(output, value)
    elif isinstance(value, str):
        _write_string(output, value, indent)
    elif isinstance(value, dict):
        _write_dict(output, value, indent)
    elif isinstance(value, (list, tuple)):
        _write_list(output, value, indent)
    else:
        raise HUMLError(f"unsupported type: {type(value)}")


def _write_number(output: IO[str], value: Union[int, float]) -> None:
    """Write a numeric value."""
    if isinstance(value, float):
        if math.isnan(value):
            output.write("nan")
        elif math.isinf(value):
            output.write("inf" if value > 0 else "-inf")
        else:
            output.write(str(value))
    else:
        output.write(str(value))


def _write_string(output: IO[str], s: str, indent: int) -> None:
    """Write a string value."""
    if '\n' in s:
        # Multiline string
        output.write('"""\n')
        lines = s.split('\n')

        # Remove empty last line if string ends with newline
        if lines and lines[-1] == '':
            lines.pop()

        content_indent = ' ' * indent
        for line in lines:
            output.write(content_indent)
            output.write(line)
            output.write('\n')

        # Closing delimiter at key indent level
        output.write(' ' * (indent - MULTILINE_INDENT))
        output.write('"""')
    else:
        # Single line string - use JSON escaping
        output.write(json.dumps(s, ensure_ascii=False))


def _write_dict(output: IO[str], d: dict, indent: int) -> None:
    """Write a dictionary."""
    if not d:
        output.write("{}")
        return

    for i, (key, value) in enumerate(d.items()):
        if i > 0:
            output.write('\n')

        # Write indentation
        output.write(' ' * indent)

        # Write key (quote if needed)
        if BARE_KEY_RE.match(key):
            output.write(key)
        else:
            output.write(json.dumps(key))

        # Write value with appropriate indicator
        is_collection = isinstance(value, (dict, list, tuple))

        if is_collection:
            if not value:  # Empty collection
                output.write(
                    f':: {"[]" if isinstance(value, (list, tuple)) else "{}"}')
            else:
                output.write('::\n')
                _write_value(output, value, indent + MULTILINE_INDENT)
        else:
            output.write(': ')
            _write_value(output, value, indent + MULTILINE_INDENT)


def _write_list(output: IO[str], lst: list, indent: int) -> None:
    """Write a list."""
    if not lst:
        output.write("[]")
        return

    for i, value in enumerate(lst):
        if i > 0:
            output.write('\n')

        output.write(' ' * indent)
        output.write('- ')

        # Check if value is a collection
        if isinstance(value, (dict, list, tuple)):
            output.write('::\n')
            _write_value(output, value, indent + MULTILINE_INDENT)
        else:
            _write_value(output, value, indent)


# Convenience functions following Python naming conventions
def load(fp: IO[str]) -> Any:
    """Load HUML from a file-like object."""
    return loads(fp.read())


def dump(obj: Any, fp: IO[str]) -> None:
    """Dump object as HUML to a file-like object."""
    fp.write(dumps(obj))
