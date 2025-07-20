# pyhuml

An experimental HUML parser implementation in Python. 

## Installation
```
pip install pyhuml
```

## Usage
```python
import pyhuml

// Parse HUML into JS data structures.
print(pyhuml.loads(huml_doc))

// Dump JS data structures into HUML.
print(pyhuml.dumps(obj))

```

### License
Licensed under the MIT license.
