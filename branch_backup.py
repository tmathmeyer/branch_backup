#!/usr/bin/env python3

import os
import subprocess
import tempfile


def RunCommand(command):
  return subprocess.run(command,
                        encoding='utf-8',
                        shell=True,
                        stderr=subprocess.PIPE,
                        stdout=subprocess.PIPE)


def _ErrorOr(cmd):
  result = RunCommand(cmd)
  if result.returncode:
    raise ValueError(f'|{cmd}|:\n {result.stderr}')
  return result.stdout.strip()


def Memoize(method):
  _memoized = None
  _hasCall = False
  def wrapper(*args):
    nonlocal _memoized
    nonlocal _hasCall
    if not _hasCall:
      _memoized = method(*args)
      _hasCall = True
    return _memoized
  return wrapper


class NTree(object):
  def __init__(self, node):
    self._node = node
    self._children = []

  def children(self):
    yield from self._children

  def node(self):
    return self._node

  def addChild(self, ntree):
    self._children.append(ntree)

  def __str__(self):
    return self._str(0)

  def __repr__(self):
    return str(self)

  def _str(self, index):
    result = ('  ' * index) + str(self._node)
    for child in self._children:
      result += ('\n' + child._str(index + 1))
    return result

  def recurse(self, method, pack):
    result = getattr(self._node, method)(pack)
    for node in self._children:
      node.recurse(method, result)
    

class GitRemote(object):
  def __init__(self, name):
    self._name = name

  @Memoize
  def getBranches(self):
    output = _ErrorOr(f'git remote show -n {self._name}')
    lines = output.split('\n')[5:]
    result = set()
    for line in lines:
      if (line.startswith('    ')):
        result.add(f'{self._name}/{line.strip()}')
      else:
        return result


class GitBranch(object):
  def __init__(self, name, upstream=None):
    self._branchname = name
    if upstream is None:
      self._upstream = self._GetUpstreamBranch()
    else:
      self._upstream = upstream
    self._aheadBehind = self.GetAheadBehind()

  def _GetUpstreamBranch(self):
    return _ErrorOr(
      f'git rev-parse --abbrev-ref {self._branchname}@{{u}}')

  def GetAheadBehind(self):
    values = _ErrorOr(f'''git rev-list --left-right \
      {self._branchname}...{self._upstream} --count''')
    values = values.split()
    return int(values[0]), int(values[1])

  def __str__(self):
    return f'{self._branchname} (upstream={self._upstream}) ({self._aheadBehind})'

  def __repr__(self):
    return str(self)

  def upstream(self):
    return self._upstream

  def name(self):
    return self._branchname

  def writePatches(self, directory):
    my_directory = os.path.join(directory, self._branchname)
    os.makedirs(my_directory)
    cmd = f'git format-patch -{self._aheadBehind[0]} {self._branchname}'
    print(cmd)
    if self._aheadBehind[1] != 0:
      raise ValueError('Please sync branches before archiving them!')

    for file in _ErrorOr(cmd).splitlines():
      os.system(f'mv {file} {my_directory}')
    return my_directory


class GitRepo(object):
  def __init__(self):
    pass

  @Memoize
  def getBranches(self):
    result = []
    branches = _ErrorOr(
      'git branch --format "%(refname:short)~%(upstream:short)"')
    for line in branches.splitlines():
      result.append(GitBranch(*line.split('~')))
    return result

  @Memoize
  def getRemotes(self):
    return [GitRemote(s) for s in _ErrorOr('git remote').splitlines()]

  @Memoize
  def getBranchesTree(self):
    remotes = self.getRemotes()
    remoteBranchNames = set()
    for remote in remotes:
      remoteBranchNames.update(remote.getBranches())

    localBranchMap = {b.name(): NTree(b) for b in self.getBranches()}
    result = {}

    for name, branch in localBranchMap.items():
      if branch.node().upstream() in remoteBranchNames:
        result[name] = branch
      elif branch.node().upstream() in localBranchMap:
        localBranchMap[branch.node().upstream()].addChild(branch)
      else:
        print(f'WARNING: branch "{name}" has no upstream!')

    return list(result.values())


class PatchTreeGenerator(object):
  def __init__(self, branchNodes):
    self._branchNodes = branchNodes
    self._tempdir = tempfile.TemporaryDirectory()

  def writePatches(self):
    for branch in self._branchNodes:
      branch.recurse('writePatches', self._tempdir.name)
    os.system(f'tree {self._tempdir.name}')
    push = f'pushd {self._tempdir.name};'
    zipd = f'zip -r branches.zip ./*;'
    popd = f'popd;'
    move = f'mv {self._tempdir.name}/branches.zip ./'
    os.system(f'{push}{zipd}{popd}{move}')


  @classmethod
  def FromGitRepo(cls):
    return cls(GitRepo().getBranchesTree())



if __name__ == '__main__':
  PatchTreeGenerator.FromGitRepo().writePatches()