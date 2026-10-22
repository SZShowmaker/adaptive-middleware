"""Assemble the relocatable, three-platform application delivery from maintained sources."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import struct

from .model import ModelError

ROOT = Path(__file__).resolve().parents[2]
PLATFORMS = ('linux-x64', 'linux-arm64', 'windows-x64')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise ModelError('generation cancelled; previous output preserved')


def safe_relative(name):
    path = Path(name)
    if path.is_absolute() or not path.parts or any(p in ('..', '.') for p in path.parts) or '\\' in name or ':' in name:
        raise ModelError('invalid package path: ' + name)
    return path


def binary_machine(path):
    with path.open('rb') as f:
        header = f.read(64)
        if len(header) < 64:
            return None
        if header[:4] == b'\x7fELF' and header[4:6] == b'\x02\x01':
            return {62: 'linux-x64', 183: 'linux-arm64'}.get(struct.unpack_from('<H', header, 18)[0])
        if header[:2] == b'MZ':
            f.seek(struct.unpack_from('<I', header, 60)[0])
            pe = f.read(6)
            if pe == b'PE\0\0\x64\x86':
                return 'windows-x64'
    return None


def profiles(config):
    entries = config.get('delivery_sdks')
    if not isinstance(entries, dict) or set(entries) != set(PLATFORMS):
        raise ModelError('config.local.json: delivery_sdks must contain linux-x64, linux-arm64 and windows-x64; see config.example.json')
    result = {}
    for platform in PLATFORMS:
        entry = entries[platform]
        if not isinstance(entry, dict) or not {'sdk_prefix', 'compiler_id', 'compiler_major'} <= entry.keys():
            raise ModelError(platform + ': sdk_prefix/compiler_id/compiler_major required')
        prefix = Path(entry['sdk_prefix']).resolve()
        if entry['compiler_id'] not in ('GNU', 'MSVC') or not re.fullmatch(r'[0-9]+', str(entry['compiler_major'])):
            raise ModelError(platform + ': invalid compiler identity')
        if (entry['compiler_id'] == 'MSVC') != (platform == 'windows-x64'):
            raise ModelError(platform + ': compiler does not match platform')
        for relative, version in [('share/fastdds/cmake/fastdds-config.cmake', '3.6.2.0'),
                                  ('lib/cmake/fastcdr/fastcdr-config.cmake', '2.3.6')]:
            source = prefix / relative
            if not source.is_file() or version not in source.read_text(encoding='utf-8'):
                raise ModelError(f'{platform}: missing/wrong-version SDK {relative}; expected {version}')
        if not any((prefix / d / 'foonathan_memory/cmake/foonathan_memory-config.cmake').is_file() for d in ('lib','share')):
            raise ModelError(platform + ': foonathan_memory SDK missing')
        libraries = ('bin/fastdds-3.6.dll', 'bin/fastcdr-2.3.dll', 'bin/foonathan_memory-0.7.4.dll') if platform == 'windows-x64' else (
            'lib/libfastdds.so', 'lib/libfastcdr.so', 'lib/libfoonathan_memory-0.7.4.so')
        for relative in libraries:
            library = prefix / relative
            if not library.is_file() or binary_machine(library) != platform:
                raise ModelError(platform + ': SDK library has wrong architecture or is missing: ' + str(library))
        for component in ('fastdds', 'fastcdr', 'foonathan_memory'):
            if not any((prefix / 'share' / component).glob('LICENSE*')):
                raise ModelError(platform + ': missing license for ' + component)
        for relative, source in entry.get('extra_files', {}).items():
            safe_relative(relative)
            if not Path(source).is_file():
                raise ModelError(platform + ': extra SDK file missing: ' + str(source))
        result[platform] = (prefix, entry)
    return result


def assemble(root, config, cancel=None):
    selected = profiles(config)
    runtime = root / 'runtime'
    for directory in ('include', 'src', 'third_party/tinyxml2'):
        shutil.copytree(ROOT / directory, runtime / directory)
    shutil.copytree(ROOT / 'tools/package', root, dirs_exist_ok=True)
    shutil.copyfile(ROOT / 'cmake/AmwRuntime.cmake', root / 'cmake/AmwRuntime.cmake')
    (root / 'config').mkdir()
    shutil.copyfile(ROOT / 'docs/app-guide/examples/logging.xml', root / 'config/logging.xml')
    metadata = {}
    for platform, (prefix, entry) in selected.items():
        destination = root / 'dependencies' / platform
        copied = {}

        def copy(source, relative):
            check_cancel(cancel)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            real = source.resolve(strict=True)
            # Resolve SDK symlinks into ordinary portable files. Hard links are
            # only between newly copied output files, never to a maintainer SDK.
            if real in copied:
                try:
                    os.link(copied[real], target)
                    return
                except OSError:
                    pass
            shutil.copyfile(real, target)
            copied[real] = target

        for directory in ('include', 'lib', 'share', 'bin'):
            for source in sorted((prefix / directory).rglob('*')):
                if source.is_file():
                    if directory == 'bin' and source.suffix.lower() != '.dll':
                        continue
                    relative = source.relative_to(prefix)
                    if source.suffix.lower() == '.cmake':
                        contents = source.read_text(encoding='utf-8')
                        if str(prefix) in contents or re.search(r'(?:^|[\"; \t])[A-Za-z]:[/\\]', contents):
                            raise ModelError(platform + ': SDK CMake is not relocatable: ' + str(relative))
                    copy(source, relative)
        for relative, source in entry.get('extra_files', {}).items():
            relative = safe_relative(relative)
            if (destination / relative).exists():
                raise ModelError(platform + ': extra file would overwrite SDK file: ' + str(relative))
            copy(Path(source), relative)
        (destination / 'profile.cmake').write_text(
            f'set(AMW_SDK_COMPILER_ID {entry["compiler_id"]})\n'
            f'set(AMW_SDK_COMPILER_MAJOR {entry["compiler_major"]})\n', encoding='utf-8')
        metadata[platform] = {'compiler_id': entry['compiler_id'], 'compiler_major': entry['compiler_major'],
                              'fastdds': '3.6.2.0', 'fastcdr': '2.3.6', 'linkage': 'shared'}
    return metadata
