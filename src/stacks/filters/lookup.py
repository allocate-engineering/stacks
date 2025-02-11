import pathlib
import json
import hashlib

import os
import hcl2

from ..cmd import config
from ..cmd import context
from ..cmd import preinit
from ..cmd import simpledb
from .. import helpers


def remote_context(ctx, stack=None, environment=None, subenvironment=None, instance=None, *args, **kwargs):  # TODO: explore if this should be a method of context.Context
    assert any([stack, environment, subenvironment, instance])
    remote_path = pathlib.Path(config.STACKS_DIR, stack or ctx.stack, config.LAYERS_DIR, (environment or ctx.env) + (f"@{subenvironment}" if subenvironment else "") + (f"_{instance}" if instance else ""))
    return context.Context(path=ctx.root_dir.joinpath(remote_path), out=ctx.work_dir.joinpath(remote_path, config.OUTPUT_DIR))


def variable(ctx, name, *args, **kwargs):
    remote_ctx = remote_context(ctx=ctx, *args, **kwargs)
    return helpers.hcl2_read(
        [
            pattern
            for pattern in [
                remote_ctx.env_dir.joinpath("env.tfvars"),
                remote_ctx.subenv_dir.joinpath("*.tfvars") if remote_ctx.subenv_dir else None,
                remote_ctx.stacks_dir.joinpath("*.tfvars"),
                remote_ctx.stack_dir.joinpath("*.tfvars"),
                remote_ctx.path.joinpath("*.tfvars"),
            ]
            if pattern
        ]
    )[name]


def get_db(ctx):
    os.makedirs(str(ctx.root_dir) + "/.stacks", exist_ok=True)
    db_filename = str(ctx.root_dir) + "/.stacks/cache"
    return simpledb.SimpleDB(db_filename)


def terraform_init_headless(ctx, argv, *args, **kwargs):
    try:
        remote_ctx = remote_context(ctx=ctx, *args, **kwargs)
        preinit.preinit(ctx=remote_ctx)
        code = helpers.hcl2_read([remote_ctx.work_dir.joinpath("*.tf")])
        helpers.directory_remove(remote_ctx.work_dir)
        helpers.json_write({"terraform": [{"backend": code["terraform"][0]["backend"]}]}, remote_ctx.universe_file)
        data = None
        helpers.run_command(config.TERRAFORM_PATH, f"-chdir={remote_ctx.work_dir}", "init")  # we cannot avoid pulling providers because we need to know the resources' schema
        data = helpers.run_command(config.TERRAFORM_PATH, f"-chdir={remote_ctx.work_dir}", *argv, interactive=False).stdout
    except Exception as e:
        if "ignore_error" in kwargs and kwargs["ignore_error"]:
            return None
        else:
            raise e

    return data


def get_stack_data(key, ctx, argv, *args, **kwargs):
    db = get_db(ctx)
    remote_ctx = remote_context(ctx=ctx, *args, **kwargs)
    cur_hashdir_val = hashdir(remote_ctx.stack_dir)
    old_hashdir_val = db.get(str(remote_ctx.stack_dir))
    cache_key = cur_hashdir_val + ":" + key
    if cur_hashdir_val == old_hashdir_val and db.has_key(cache_key):
        return db.get(cache_key)
    else:
        content = terraform_init_headless(ctx, argv, *args, **kwargs)
        if content:
            db.delete(str(remote_ctx.stack_dir))
            db.set(str(remote_ctx.stack_dir), cur_hashdir_val)
            db.set(cache_key, content)

        return content


def output(ctx, name, *args, **kwargs):
    if ctx.ancestor == ctx.parent and ctx.parent is not None:
        return ""  # empty string so it cannot be iterated upon

    data = get_stack_data(key=name, ctx=ctx, argv=["output", "-json", name], *args, **kwargs)
    if data:
        loaded_data = json.loads(data)
        if "format" not in kwargs or kwargs["format"]:
            return json.dumps(loaded_data)
        else:
            return loaded_data

    return None


def resource(ctx, address, *args, **kwargs):
    if ctx.ancestor == ctx.parent and ctx.parent is not None:
        return ""  # empty string so it cannot be iterated upon

    data = get_stack_data(key=address, ctx=ctx, argv=["state", "show", "-no-color", address], *args, **kwargs)
    return hcl2.loads(data)["resource"][0].popitem()[1].popitem()[1]


def hashdir(dirname, followlinks=False):
    exclude = [config.OUTPUT_DIR]
    hashvalues = []
    hash_func = hashlib.sha512

    for root, dirs, files in os.walk(dirname, topdown=True, followlinks=followlinks):
        dirs[:] = [d for d in dirs if d not in exclude]

        dirs.sort()
        files.sort()

        for fname in files:
            if fname.startswith(".") or fname == "":
                continue

            hashvalues.append(_filehash(os.path.join(root, fname), hash_func))

    return _reduce_hash(hashvalues, hash_func)


def _filehash(filepath, hashfunc):
    hasher = hashfunc()
    blocksize = 64 * 1024

    if not os.path.exists(filepath):
        return hasher.hexdigest()

    with open(filepath, "rb") as fp:
        while True:
            data = fp.read(blocksize)
            if not data:
                break
            hasher.update(data)
    return hasher.hexdigest()


def _reduce_hash(hashlist, hashfunc):
    hasher = hashfunc()
    for hashvalue in sorted(hashlist):
        hasher.update(hashvalue.encode("utf-8"))
    return hasher.hexdigest()
