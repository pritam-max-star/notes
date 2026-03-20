# CLI Anagram Finder

A command-line tool to store, find, and group anagrams using a HashMap-based approach.

## Concepts

- **HashMap** — words are indexed by `frozenset(Counter(word).items())`, a character frequency map. All anagrams share the same key, enabling O(1) lookup.
- **File I/O** — `words.txt` is the persistent word store. `_load()` reads it into a `dict[frozenset, list[str]]` at runtime; `_save()` flattens it back to a plain word list.
- **String Manipulation** — all matching is case-insensitive; original casing is preserved in the store.

## How It Works

```
words.txt  ──→  _load()  ──→  dict[frozenset, list[str]]  ──→  find / group / export
   ↑                                                                      │
   └──────────────────────  _save()  ←────────────────────────────── add()
```

`words.txt` is the source of truth. The dict is a transient structure rebuilt on every operation — not persisted to disk. You can also edit `words.txt` manually; the tool will pick up changes automatically.

## Usage

```bash
# Add words to the store
python anagram.py add listen silent enlist inlets google python

# Check if two words are anagrams of each other
python anagram.py check listen silent

# Find all anagrams of a word within the store
python anagram.py find listen

# Group all words in the store by anagram family
python anagram.py group

# Export grouped families to a file
python anagram.py export results.txt
```

## Example Output

```
$ python anagram.py check listen silent
"listen" and "silent" are anagrams.

$ python anagram.py find listen
Anagrams of 'listen': silent, enlist, inlets

$ python anagram.py group
Group 1: listen, silent, enlist, inlets
Group 2: google
Group 3: python
```

## File Structure

```
week1_cli_anagram/
├── anagram.py       # All logic + CLI entry point
├── words.txt        # Persistent word store (auto-created on first add)
├── test_anagram.py  # Unit tests
└── README.md
```

## Running Tests

```bash
python -m unittest test_anagram -v
```
