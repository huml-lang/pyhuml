# pyhuml

An experimental HUML parser implementation in Python. 

## Installation
```
pip install pyhuml
```

## Usage
```python
import pyhuml

# Parse HUML into Python data structures.
print(pyhuml.loads(huml_doc))

# Dump Python data structures into HUML.
print(pyhuml.dumps(obj))

```

### License
Licensed under the MIT license.
