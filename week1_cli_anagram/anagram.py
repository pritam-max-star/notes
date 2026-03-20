import argparse
from collections import Counter
from pathlib import Path

STORE = Path(__file__).parent / "words.txt"


class AnagramStore:
    def _key(self, word: str) -> frozenset:
        return frozenset(Counter(word.lower()).items())

    def _load(self) -> dict[frozenset, list[str]]:
        store: dict[frozenset, list[str]] = {}
        if not STORE.exists():
            return store
        for word in STORE.read_text().splitlines():
            if word:
                store.setdefault(self._key(word), []).append(word)
        return store

    def _save(self, store: dict[frozenset, list[str]]) -> None:
        words = [word for group in store.values() for word in group]
        STORE.write_text("\n".join(words))

    def add(self, words: list[str]) -> None:
        store = self._load()
        existing_lower = {w.lower() for group in store.values() for w in group}
        new_words = [w for w in words if w.lower() not in existing_lower]
        if not new_words:
            print("All words already in store.")
            return
        for word in new_words:
            store.setdefault(self._key(word), []).append(word)
        self._save(store)
        print(f"Added: {', '.join(new_words)}")

    def check(self, w1: str, w2: str) -> None:
        result = Counter(w1.lower()) == Counter(w2.lower())
        print(f'"{w1}" and "{w2}" are{"" if result else " NOT"} anagrams.')

    def find(self, word: str) -> None:
        store = self._load()
        matches = [w for w in store.get(self._key(word), []) if w.lower() != word.lower()]
        if matches:
            print(f"Anagrams of '{word}': {', '.join(matches)}")
        else:
            print(f"No anagrams of '{word}' found in store.")

    def group(self) -> None:
        store = self._load()
        if not store:
            print("Store is empty.")
            return
        for i, group in enumerate(store.values(), 1):
            print(f"Group {i}: {', '.join(group)}")

    def export(self, path: str) -> None:
        store = self._load()
        if not store:
            print("Store is empty.")
            return
        lines = [
            f"Group {i}: {', '.join(group)}"
            for i, group in enumerate(store.values(), 1)
        ]
        Path(path).write_text("\n".join(lines))
        print(f"Exported {len(store)} group(s) to '{path}'.")


def main():
    parser = argparse.ArgumentParser(prog="anagram", description="CLI Anagram Finder")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="Add words to the store")
    p_add.add_argument("words", nargs="+")

    p_check = sub.add_parser("check", help="Check if two words are anagrams")
    p_check.add_argument("w1")
    p_check.add_argument("w2")

    p_find = sub.add_parser("find", help="Find anagrams of a word from store")
    p_find.add_argument("word")

    sub.add_parser("group", help="Group all store words by anagram family")

    p_export = sub.add_parser("export", help="Export grouped families to a file")
    p_export.add_argument("output")

    args = parser.parse_args()
    store = AnagramStore()

    if args.cmd == "add":        store.add(args.words)
    elif args.cmd == "check":   store.check(args.w1, args.w2)
    elif args.cmd == "find":    store.find(args.word)
    elif args.cmd == "group":   store.group()
    elif args.cmd == "export":  store.export(args.output)


if __name__ == "__main__":
    main()
