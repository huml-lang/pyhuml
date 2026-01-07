# pyhuml

An experimental HUML parser implementation in Python. 

## Installation
```
pip install pyhuml
```

## Usage
```python
import pyhuml

humlDoc = """\
# A sample HUML document.
website::
  hostname: "huml.io"
  ports:: 80, 443
  enabled: true
  factor: 3.14
  props:: mime_type: "text/html", encoding: "gzip"
  tags:: # Multi-line list.
    - "markup"
    - "webpage"
    - "schema"

haikus::
  one: \"\"\"
    A quiet language
    Lines fall into their places
    Nothing out of place
  \"\"\"
"""

# Parse HUML into Python data structures.
obj = pyhuml.loads(humlDoc)
print("Parsed Object:",obj)

# Dump Python data structures into HUML.
huml_output = pyhuml.dumps(obj)
print("Serialized Output:\n",huml_output)
```

### License
Licensed under the MIT license.
