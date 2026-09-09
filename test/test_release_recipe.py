"""A new model packages with data only; no OpenArmX repository or code branch."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT.parent / 'humanoid_manager/test'))
from humanoid_manager.deployment import pack_directory
from test_deployment_plugins import _hardware_tree, _model_tree


def test_generic_release_recipe_validates_complete_import(tmp_path):
    spec = importlib.util.spec_from_file_location('create_release', ROOT / 'scripts/create_release.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    manifest = tmp_path / 'workspace.repos'
    manifest.write_text(json.dumps({'repositories': {}, 'profiles': {'bench': {'repositories': []}}}))
    specs = []
    for role, factory in [('driver', _hardware_tree), ('model', _model_tree)]:
        archive = pack_directory(factory(tmp_path / role), tmp_path / f'{role}.zip')
        specs.append({'role': role, 'command': [sys.executable, '-c',
            'import shutil,sys; shutil.copyfile(sys.argv[1],sys.argv[2])', str(archive), '${output}']})
    recipe = tmp_path / 'recipe.json'
    recipe.write_text(json.dumps({'schema_version': 1, 'robot_id': 'new_machine', 'name': 'New machine', 'plugins': specs}))
    output = module.build_release(tmp_path, tmp_path / 'release', manifest, recipe=recipe, profile='bench')
    assert (output / 'new_machine-complete.zip').is_file()
    report = json.loads((output / 'source-revisions.json').read_text())
    assert report['manager_import_apply_verified']
    assert report['robot_id'] == 'new_machine'
    assert not report['hardware_verified']
