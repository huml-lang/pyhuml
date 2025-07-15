"""
pyhuml - A Python implementation of HUML (Human-Oriented Markup Language)

HUML is a machine-readable markup language with a focus on readability by humans.
It borrows YAML's visual appearance, but avoids its complexities and ambiguities.
"""

import re
import math
import json
from typing import Any, Dict, List, Union, Optional, IO, Tuple
from io import StringIO
from dataclasses import dataclass, field


# Precompiled regular expressions
BARE_KEY_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]*$')
VERSION_RE = re.compile(r'^v\d+\.\d+\.\d+$')


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
    
    def peek_char(self, offset: int = 0) -> Optional[str]:
        """Peek at character at current position + offset."""
        pos = self.pos + offset
        if 0 <= pos < len(self.data):
            return self.data[pos]
        return None
    
    def peek_string(self, s: str) -> bool:
        """Check if string s appears at current position."""
        end = self.pos + len(s)
        if end > len(self.data):
            return False
        return self.data[self.pos:end] == s
    
    def advance(self, n: int = 1):
        """Advance position by n characters."""
        self.pos += n
    
    def skip_spaces(self):
        """Skip space characters (not newlines)."""
        while not self.done() and self.data[self.pos] == ' ':
            self.pos += 1
    
    def get_cur_indent(self) -> int:
        """Get indentation level of current line."""
        line_start = self._line_start()
        indent = 0
        while line_start + indent < len(self.data) and self.data[line_start + indent] == ' ':
            indent += 1
        return indent
    
    def _line_start(self) -> int:
        """Find the start position of current line."""
        start = self.pos
        if start > 0 and start <= len(self.data) and self.data[start - 1] == '\n':
            return start
        
        while start > 0 and self.data[start - 1] != '\n':
            start -= 1
        return start
    
    def consume_line(self) -> None:
        """Consume rest of line, validating no trailing spaces."""
        content_start = self.pos
        self.skip_spaces()
        
        if self.done() or self.data[self.pos] == '\n':
            if self.pos > content_start:
                raise self.error("trailing spaces are not allowed")
        elif self.data[self.pos] == '#':
            if self.pos == content_start and self.get_cur_indent() != self.pos - self._line_start():
                raise self.error("a value must be separated from an inline comment by a space")
            
            # Consume '#'
            self.pos += 1
            if not self.done() and self.data[self.pos] != ' ' and self.data[self.pos] != '\n':
                raise self.error("comment hash '#' must be followed by a space")
        else:
            raise self.error("unexpected content at end of line")
        
        # Skip to end of line
        comment_end = self.pos
        while not self.done() and self.data[self.pos] != '\n':
            self.pos += 1
        
        # Check for trailing spaces
        if self.pos > 0 and self.data[self.pos - 1] == ' ':
            if self.pos - 1 > comment_end:
                raise self.error("trailing spaces are not allowed")
        
        # Consume newline
        if not self.done() and self.data[self.pos] == '\n':
            self.pos += 1
            self.line += 1
    
    def consume_line_content(self) -> str:
        """Read rest of line without validation (for multiline strings)."""
        start = self.pos
        while not self.done() and self.data[self.pos] != '\n':
            self.pos += 1
        
        content = self.data[start:self.pos]
        if not self.done() and self.data[self.pos] == '\n':
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
            
            if self.data[self.pos] not in ('\n', '#'):
                return
            
            # Check for trailing spaces on blank lines
            if self.data[self.pos] == '\n' and self.pos > line_start:
                raise self.error("trailing spaces are not allowed")
            
            # Reset and consume the line
            self.pos = line_start
            self.consume_line()
    
    def assert_space(self, context: str) -> None:
        """Ensure exactly one space at current position."""
        if self.done() or self.data[self.pos] != ' ':
            raise self.error(f"expected single space {context}")
        
        self.advance()
        if not self.done() and self.data[self.pos] == ' ':
            raise self.error(f"expected single space {context}, found multiple")
    
    def expect_comma(self) -> None:
        """Consume a comma with correct spacing."""
        self.skip_spaces()
        if self.done() or self.data[self.pos] != ',':
            raise self.error("expected a comma in inline collection")
        
        if self.pos > 0 and self.data[self.pos - 1] == ' ':
            raise self.error("no spaces allowed before comma")
        
        self.advance()
        self.assert_space("after comma")


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
        output.write("%HUML v0.1.0\n")
    
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
            
            # Parse version string
            start = p.pos
            while not p.done() and p.data[p.pos] not in (' ', '\n', '#'):
                p.pos += 1
            
            if p.pos > start:
                version = p.data[start:p.pos]
                if version != "v0.1.0":
                    raise p.error(f"unsupported version '{version}'. expected 'v0.1.0'")
        
        p.consume_line()
    
    # Skip blank lines and comments
    p.skip_blank_lines()
    
    if p.done():
        raise p.error("empty document is undefined")
    
    # Root element must not be indented
    if p.get_cur_indent() != 0:
        raise p.error("root element must not be indented")
    
    # Check for forbidden root indicators
    if p.peek_string("::"):
        raise p.error("'::' indicator not allowed at document root")
    if p.peek_string(":") and not _has_key_value_pair(p):
        raise p.error("':' indicator not allowed at document root")
    
    # Determine document type and parse
    doc_type = _get_root_type(p)
    
    if doc_type == 'inline_dict':
        result = _parse_inline_dict_contents(p)
        return _assert_root_end(p, result, "root inline dict")
    
    elif doc_type == 'multiline_dict':
        return _parse_multiline_dict(p, 0)
    
    elif doc_type == 'empty_list':
        p.advance(2)
        p.consume_line()
        return _assert_root_end(p, [], "root list")
    
    elif doc_type == 'empty_dict':
        p.advance(2)
        p.consume_line()
        return _assert_root_end(p, {}, "root dict")
    
    elif doc_type == 'multiline_list':
        return _parse_multiline_list(p, 0)
    
    elif doc_type == 'inline_list':
        result = _parse_inline_list_contents(p)
        return _assert_root_end(p, result, "root inline list")
    
    elif doc_type == 'scalar':
        result = _parse_value(p, 0)
        p.consume_line()
        return _assert_root_end(p, result, "root scalar value")
    
    else:
        raise p.error("internal error: unknown document type")


def _get_root_type(p: Parser) -> str:
    """Determine the type of the root document."""
    if _has_key_value_pair(p):
        if _has_inline_dict_at_root(p):
            return 'inline_dict'
        return 'multiline_dict'
    
    if p.peek_string("[]"):
        return 'empty_list'
    if p.peek_string("{}"):
        return 'empty_dict'
    
    if p.peek_char() == '-':
        return 'multiline_list'
    
    if _has_inline_list_at_root(p):
        return 'inline_list'
    
    return 'scalar'


def _assert_root_end(p: Parser, result: Any, description: str) -> Any:
    """Ensure no content follows root element."""
    p.skip_blank_lines()
    if not p.done():
        raise p.error(f"unexpected content after {description}")
    return result


def _has_key_value_pair(p: Parser) -> bool:
    """Check if current line has a key: value pattern."""
    saved_pos = p.pos
    try:
        _parse_key(p)
        return not p.done() and p.data[p.pos] == ':'
    except:
        return False
    finally:
        p.pos = saved_pos


def _has_inline_dict_at_root(p: Parser) -> bool:
    """Check if root starts with inline dict pattern."""
    pos = p.pos
    has_colon = False
    has_comma = False
    has_double_colon = False
    
    # Check current line for patterns
    while pos < len(p.data) and p.data[pos] not in ('\n', '#'):
        if p.data[pos] == ':':
            if pos + 1 < len(p.data) and p.data[pos + 1] == ':':
                has_double_colon = True
            else:
                has_colon = True
        if p.data[pos] == ',':
            has_comma = True
        pos += 1
    
    if not (has_colon and has_comma and not has_double_colon):
        return False
    
    # Check if there's content after this line
    while pos < len(p.data) and p.data[pos] != '\n':
        pos += 1
    if pos < len(p.data) and p.data[pos] == '\n':
        pos += 1
    
    # Skip blank lines and comments
    while pos < len(p.data):
        # Skip spaces
        while pos < len(p.data) and p.data[pos] == ' ':
            pos += 1
        
        if pos >= len(p.data):
            break
        
        if p.data[pos] == '\n':
            pos += 1
            continue
        
        if p.data[pos] == '#':
            while pos < len(p.data) and p.data[pos] != '\n':
                pos += 1
            if pos < len(p.data) and p.data[pos] == '\n':
                pos += 1
            continue
        
        # Found non-blank, non-comment content
        return False
    
    return True


def _has_inline_list_at_root(p: Parser) -> bool:
    """Check if root starts with inline list pattern."""
    pos = p.pos
    while pos < len(p.data) and p.data[pos] not in ('\n', '#'):
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
        if p.done():
            break
        
        cur_indent = p.get_cur_indent()
        if cur_indent < indent:
            break
        
        if cur_indent != indent:
            raise p.error(f"bad indent {cur_indent}, expected {indent}")
        
        if not _is_key_start(p):
            raise p.error(f"invalid character '{p.data[p.pos]}', expected key")
        
        # Parse key
        key = _parse_key(p)
        
        if key in result:
            raise p.error(f"duplicate key '{key}' in dict")
        
        # Parse indicator
        indicator = _parse_indicator(p)
        
        if indicator == ':':
            p.assert_space("after ':'")
            
            # Check if multiline string
            is_multiline = p.peek_string("```") or p.peek_string('"""')
            
            value = _parse_value(p, cur_indent)
            
            if not is_multiline:
                p.consume_line()
        else:  # '::'
            value = _parse_vector(p, cur_indent + 2)
        
        result[key] = value
    
    return result


def _parse_multiline_list(p: Parser, indent: int) -> List[Any]:
    """Parse a multiline list."""
    result = []
    
    while True:
        p.skip_blank_lines()
        if p.done():
            break
        
        cur_indent = p.get_cur_indent()
        if cur_indent < indent:
            break
        
        if cur_indent != indent:
            raise p.error(f"bad indent {cur_indent}, expected {indent}")
        
        if p.data[p.pos] != '-':
            break
        
        p.advance()
        p.assert_space("after '-'")
        
        # Check for nested vector
        if p.peek_string("::"):
            p.advance(2)
            value = _parse_vector(p, cur_indent + 2)
        else:
            value = _parse_value(p, cur_indent)
            p.consume_line()
        
        result.append(value)
    
    return result


def _parse_vector(p: Parser, indent: int) -> Union[List, Dict]:
    """Parse a vector (list or dict) after :: indicator."""
    start_pos = p.pos
    p.skip_spaces()
    
    # Check for multiline vector
    if p.done() or p.data[p.pos] == '\n' or p.data[p.pos] == '#':
        p.pos = start_pos
        p.consume_line()
        
        # Determine vector type
        vec_type = _get_multiline_vector_type(p, indent)
        
        if vec_type == 'list':
            return _parse_multiline_list(p, p.get_cur_indent())
        else:
            return _parse_multiline_dict(p, p.get_cur_indent())
    
    # Inline vector - must have exactly one space
    p.pos = start_pos
    p.assert_space("after '::'")
    
    return _parse_inline_vector(p)


def _get_multiline_vector_type(p: Parser, indent: int) -> str:
    """Determine if multiline vector is list or dict."""
    p.skip_blank_lines()
    
    if p.done():
        raise p.error("ambiguous empty vector after '::'. Use [] or {}.")
    
    cur_indent = p.get_cur_indent()
    if cur_indent < indent:
        raise p.error("ambiguous empty vector after '::'. Use [] or {}.")
    
    if p.data[p.pos] == '-':
        return 'list'
    return 'dict'


def _parse_inline_vector(p: Parser) -> Union[List, Dict]:
    """Parse inline vector (list or dict)."""
    # Check for empty markers
    if p.peek_string("[]"):
        p.advance(2)
        p.consume_line()
        return []
    
    if p.peek_string("{}"):
        p.advance(2)
        p.consume_line()
        return {}
    
    # Determine if dict or list
    if _has_inline_dict(p):
        return _parse_inline_dict_contents(p)
    else:
        return _parse_inline_list_contents(p)


def _has_inline_dict(p: Parser) -> bool:
    """Check if inline collection is a dict."""
    pos = p.pos
    while pos < len(p.data) and p.data[pos] not in ('\n', '#'):
        if p.data[pos] == ':':
            if pos + 1 < len(p.data) and p.data[pos + 1] != ':':
                return True
        pos += 1
    return False


def _parse_inline_dict_contents(p: Parser) -> Dict[str, Any]:
    """Parse inline dictionary contents."""
    result = {}
    is_first = True
    
    while not p.done() and p.data[p.pos] not in ('\n', '#'):
        if not is_first:
            p.expect_comma()
        is_first = False
        
        key = _parse_key(p)
        
        if p.done() or p.data[p.pos] != ':':
            raise p.error("expected ':' in inline dict")
        
        p.advance()
        p.assert_space("in inline dict")
        
        value = _parse_value(p, 0)
        result[key] = value
        
        # Skip spaces only if comma follows
        if not p.done() and p.data[p.pos] == ' ':
            next_pos = p.pos + 1
            while next_pos < len(p.data) and p.data[next_pos] == ' ':
                next_pos += 1
            if next_pos < len(p.data) and p.data[next_pos] == ',':
                p.skip_spaces()
    
    p.consume_line()
    return result


def _parse_inline_list_contents(p: Parser) -> List[Any]:
    """Parse inline list contents."""
    result = []
    is_first = True
    
    while not p.done() and p.data[p.pos] not in ('\n', '#'):
        if not is_first:
            p.expect_comma()
        is_first = False
        
        value = _parse_value(p, 0)
        result.append(value)
        
        # Skip spaces only if comma follows
        if not p.done() and p.data[p.pos] == ' ':
            next_pos = p.pos + 1
            while next_pos < len(p.data) and p.data[next_pos] == ' ':
                next_pos += 1
            if next_pos < len(p.data) and p.data[next_pos] == ',':
                p.skip_spaces()
    
    p.consume_line()
    return result


def _parse_key(p: Parser) -> str:
    """Parse a dictionary key."""
    p.skip_spaces()
    
    if p.peek_char() == '"':
        return _parse_string(p)
    
    # Bare key
    start = p.pos
    while not p.done() and (p.data[p.pos].isalnum() or p.data[p.pos] in '-_'):
        p.pos += 1
    
    if p.pos == start:
        raise p.error("expected a key")
    
    return p.data[start:p.pos]


def _parse_indicator(p: Parser) -> str:
    """Parse : or :: indicator."""
    if p.done() or p.data[p.pos] != ':':
        raise p.error("expected ':' or '::' after key")
    
    p.advance()
    if not p.done() and p.data[p.pos] == ':':
        p.advance()
        return '::'
    
    return ':'


def _parse_value(p: Parser, key_indent: int) -> Any:
    """Parse any scalar value."""
    if p.done():
        raise p.error("unexpected end of input, expected a value")
    
    c = p.data[p.pos]
    
    # String
    if c == '"':
        if p.peek_string('"""'):
            return _parse_multiline_string(p, key_indent, strip_spaces=True)
        return _parse_string(p)
    
    # Multiline string with backticks
    if c == '`' and p.peek_string('```'):
        return _parse_multiline_string(p, key_indent, strip_spaces=False)
    
    # Boolean
    if c == 't' and p.peek_string('true'):
        p.advance(4)
        return True
    if c == 'f' and p.peek_string('false'):
        p.advance(5)
        return False
    
    # Null
    if c == 'n' and p.peek_string('null'):
        p.advance(4)
        return None
    
    # Special numeric values
    if c == 'n' and p.peek_string('nan'):
        p.advance(3)
        return float('nan')
    
    if c == 'i' and p.peek_string('inf'):
        p.advance(3)
        return float('inf')
    
    if c == '+':
        p.advance()
        if p.peek_string('inf'):
            p.advance(3)
            return float('inf')
        if _is_digit(p.peek_char()):
            p.pos -= 1
            return _parse_number(p)
        raise p.error("invalid character after '+'")
    
    if c == '-':
        p.advance()
        if p.peek_string('inf'):
            p.advance(3)
            return float('-inf')
        if _is_digit(p.peek_char()):
            p.pos -= 1
            return _parse_number(p)
        raise p.error("invalid character after '-'")
    
    # Number
    if _is_digit(c):
        return _parse_number(p)
    
    raise p.error(f"unexpected character '{c}' when parsing value")


def _parse_string(p: Parser) -> str:
    """Parse a quoted string."""
    p.advance()  # Skip opening quote
    
    result = []
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
            if esc in ('"', '\\', '/'):
                result.append(esc)
            elif esc == 'n':
                result.append('\n')
            elif esc == 't':
                result.append('\t')
            elif esc == 'r':
                result.append('\r')
            elif esc == 'b':
                result.append('\b')
            elif esc == 'f':
                result.append('\f')
            elif esc == 'u':
                # Unicode escape
                if p.pos + 4 >= len(p.data):
                    raise p.error("incomplete unicode escape sequence \\u")
                hex_digits = p.data[p.pos + 1:p.pos + 5]
                try:
                    code = int(hex_digits, 16)
                    result.append(chr(code))
                except ValueError:
                    raise p.error(f"invalid unicode escape sequence \\u{hex_digits}")
                p.advance(4)
            else:
                raise p.error(f"invalid escape character '\\{esc}'")
        else:
            result.append(c)
        
        p.advance()
    
    raise p.error("unclosed string")


def _parse_multiline_string(p: Parser, key_indent: int, strip_spaces: bool) -> str:
    """Parse multiline string (``` or \"\"\")."""
    delim = p.data[p.pos:p.pos + 3]
    p.advance(3)
    
    p.consume_line()
    
    lines = []
    
    while not p.done():
        line_start = p.pos
        line_indent = 0
        
        # Count indentation
        while not p.done() and p.data[p.pos] == ' ':
            line_indent += 1
            p.pos += 1
        
        # Check for closing delimiter
        if p.peek_string(delim):
            if line_indent != key_indent:
                raise p.error(f"multiline closing delimiter must be at same indentation as the key ({key_indent} spaces)")
            
            p.advance(3)
            p.consume_line()
            
            # Join lines and remove final newline
            return '\n'.join(lines)
        
        # Get line content
        p.pos = line_start
        line_content = p.consume_line_content()
        
        # Process line based on string type
        if strip_spaces:
            # Strip all leading and trailing whitespace
            processed = line_content.strip()
        else:
            # Strip required indent (key_indent + 2)
            req_indent = key_indent + 2
            if len(line_content) >= req_indent and line_content[:req_indent].strip() == '':
                processed = line_content[req_indent:]
            else:
                processed = line_content
        
        lines.append(processed)
    
    raise p.error("unclosed multiline string")


def _parse_number(p: Parser) -> Union[int, float]:
    """Parse numeric value."""
    start = p.pos
    
    # Handle sign
    if p.peek_char() in ('+', '-'):
        p.advance()
    
    # Check for special bases
    if p.peek_string("0x"):
        return _parse_base(p, start, 16, "0x")
    if p.peek_string("0o"):
        return _parse_base(p, start, 8, "0o")
    if p.peek_string("0b"):
        return _parse_base(p, start, 2, "0b")
    
    # Parse decimal number
    is_float = False
    
    while not p.done():
        c = p.data[p.pos]
        
        if _is_digit(c) or c == '_':
            p.advance()
        elif c == '.':
            is_float = True
            p.advance()
        elif c in ('e', 'E'):
            is_float = True
            p.advance()
            if p.peek_char() in ('+', '-'):
                p.advance()
        else:
            break
    
    # Parse the number
    num_str = p.data[start:p.pos].replace('_', '')
    
    try:
        if is_float:
            return float(num_str)
        else:
            return int(num_str)
    except ValueError as e:
        raise p.error(f"invalid number: {e}")


def _parse_base(p: Parser, start: int, base: int, prefix: str) -> int:
    """Parse number in specific base."""
    p.advance(len(prefix))
    num_start = p.pos
    
    while not p.done():
        c = p.data[p.pos]
        valid = False
        
        if base == 16:
            valid = _is_hex(c)
        elif base == 8:
            valid = '0' <= c <= '7'
        elif base == 2:
            valid = c in ('0', '1')
        
        if not valid:
            break
        p.advance()
    
    if p.pos == num_start:
        raise p.error("invalid number literal, requires digits after prefix")
    
    # Get sign
    sign = ''
    if p.data[start] in ('+', '-'):
        sign = p.data[start]
    
    # Parse number
    num_str = p.data[num_start:p.pos].replace('_', '')
    try:
        val = int(num_str, base)
        if sign == '-':
            return -val
        return val
    except ValueError as e:
        raise p.error(f"invalid number: {e}")


def _is_key_start(p: Parser) -> bool:
    """Check if current position could start a key."""
    return not p.done() and (p.data[p.pos] == '"' or p.data[p.pos].isalpha())


def _is_digit(c: Optional[str]) -> bool:
    """Check if character is a digit."""
    return c is not None and '0' <= c <= '9'


def _is_hex(c: str) -> bool:
    """Check if character is a hex digit."""
    return _is_digit(c) or ('a' <= c <= 'f') or ('A' <= c <= 'F')


def _write_value(output: IO[str], value: Any, indent: int) -> None:
    """Write a value to output in HUML format."""
    if value is None:
        output.write("null")
    
    elif isinstance(value, bool):
        output.write("true" if value else "false")
    
    elif isinstance(value, (int, float)):
        if isinstance(value, float):
            if math.isnan(value):
                output.write("nan")
            elif math.isinf(value):
                output.write("inf" if value > 0 else "-inf")
            else:
                # Use Python's default float formatting
                output.write(str(value))
        else:
            output.write(str(value))
    
    elif isinstance(value, str):
        _write_string(output, value, indent)
    
    elif isinstance(value, dict):
        _write_dict(output, value, indent)
    
    elif isinstance(value, (list, tuple)):
        _write_list(output, value, indent)
    
    else:
        raise HUMLError(f"unsupported type: {type(value)}")


def _write_string(output: IO[str], s: str, indent: int) -> None:
    """Write a string value."""
    if '\n' in s:
        # Multiline string
        key_indent = indent - 2
        content_indent = indent
        
        output.write("```\n")
        lines = s.split('\n')
        
        # Remove empty last line if string ends with newline
        if lines and lines[-1] == '':
            lines = lines[:-1]
        
        for line in lines:
            output.write(' ' * content_indent)
            output.write(line)
            output.write('\n')
        
        output.write(' ' * key_indent)
        output.write("```")
    else:
        # Single line string - use JSON-style escaping
        output.write(json.dumps(s))


def _write_dict(output: IO[str], d: dict, indent: int) -> None:
    """Write a dictionary."""
    if not d:
        output.write("{}")
        return
    
    items = list(d.items())
    
    for i, (key, value) in enumerate(items):
        if i > 0:
            output.write('\n')
        
        _write_key_value(output, key, value, indent)


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
            _write_value(output, value, indent + 2)
        else:
            _write_value(output, value, indent)


def _write_key_value(output: IO[str], key: str, value: Any, indent: int) -> None:
    """Write a key-value pair."""
    output.write(' ' * indent)
    
    # Quote key if needed
    if BARE_KEY_RE.match(key):
        output.write(key)
    else:
        output.write(json.dumps(key))
    
    # Determine if value is collection
    is_collection = isinstance(value, (dict, list, tuple))
    
    if is_collection:
        if (isinstance(value, dict) and not value) or \
           (isinstance(value, (list, tuple)) and not value):
            # Empty collection
            output.write(':: ')
        else:
            # Non-empty collection
            output.write('::\n')
    else:
        output.write(': ')
    
    _write_value(output, value, indent + 2)


# Convenience function following Python naming conventions
def load(fp: IO[str]) -> Any:
    """Load HUML from a file-like object."""
    return loads(fp.read())


def dump(obj: Any, fp: IO[str]) -> None:
    """Dump object as HUML to a file-like object."""
    fp.write(dumps(obj))
