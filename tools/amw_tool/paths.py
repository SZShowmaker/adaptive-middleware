"""Project-scoped editor and default CLI locations (not part of the model)."""
from pathlib import Path
from .model import ModelError, name


def project_paths(root, project_id, delivery_root=''):
    name(project_id, 'project_id')
    # IDs also become directory names on Windows.
    if project_id.upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1, 10)), *('LPT'+str(i) for i in range(1, 10))}:
        raise ModelError('project_id: reserved directory name')
    root = Path(root).resolve()
    if not isinstance(delivery_root, str):
        raise ModelError('delivery_root: expected absolute path or empty string')
    base = Path(delivery_root).expanduser() if delivery_root else root/'out/delivery'
    if not base.is_absolute():
        raise ModelError('delivery_root: use an absolute path on the GUI server')
    base = base.resolve()
    draft_base = (root/'out/editor').resolve()
    draft = draft_base/project_id
    output = base/project_id/'src-gen'
    for path, parent in ((draft, draft_base), (output, base)):
        if path.resolve() != path:
            raise ModelError('project directory must not redirect through a symlink: '+str(path))
        if parent.exists() and not parent.is_dir():
            raise ModelError('parent is not a directory: '+str(parent))
    return {'draft': str(draft), 'project_file': str(draft/'project.cm.json'),
            'output': str(output), 'delivery_root': str(base)}
