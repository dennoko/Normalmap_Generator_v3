import os
import xml.etree.ElementTree as ET

# Simple i18n loader using XML resource files placed under normalmap_generator/i18n

class I18n:
    def __init__(self, pkg_dir=None, default_lang='ja'):
        if pkg_dir is None:
            pkg_dir = os.path.dirname(__file__)
        self.i18n_dir = os.path.join(pkg_dir, 'i18n')
        self.language = default_lang
        self.strings = {}
        # load default immediately
        self._load_language(self.language)

    def _load_language(self, lang):
        path = os.path.join(self.i18n_dir, f'strings_{lang}.xml')
        if not os.path.exists(path):
            # missing file: keep empty but don't crash
            self.strings = {}
            return
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            data = {}
            for s in root.findall('string'):
                key = s.get('key')
                if key:
                    data[key] = s.text or ''
            self.strings = data
        except Exception:
            self.strings = {}

    def set_language(self, lang_code):
        self.language = lang_code
        self._load_language(lang_code)

    def get(self, key, **kwargs):
        # return the localized string; if not found, return the key itself
        val = self.strings.get(key)
        if val is None:
            # try fallback to Japanese if current isn't ja
            if self.language != 'ja':
                fallback_path = os.path.join(self.i18n_dir, 'strings_ja.xml')
                try:
                    tree = ET.parse(fallback_path)
                    root = tree.getroot()
                    for s in root.findall('string'):
                        if s.get('key') == key:
                            val = s.text or ''
                            break
                except Exception:
                    val = None
        if val is None:
            val = key
        try:
            return val.format(**kwargs)
        except Exception:
            return val

# module-level default instance
_i18n = I18n()


def set_language(lang_code):
    _i18n.set_language(lang_code)


def get(key, **kwargs):
    return _i18n.get(key, **kwargs)


def current_language():
    return _i18n.language
