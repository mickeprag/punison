#!/usr/bin/env python

import getopt, hashlib, os, shutil, sys
import ConfigParser, pickle

class File(object):
	def __init__(self, path, filename):
		self.path = path
		self.filename = filename
		self.localModified = None
		self.remoteModified = None
		self.hash = None
		self.removed = False

	def calculateHash(self, basepath):
		path = os.path.join(basepath, self.path, self.filename)
		f = open(path, 'rb')
		hash = hashlib.sha1()
		while True:
			data = f.read(1024)
			if not data:
				break
			hash.update(data)
		f.close()
		return hash.hexdigest()

	def fileExists(self, basepath):
		return os.path.exists(os.path.join(basepath, self.path, self.filename))

	def updateIfNeeded(self, localPath, remotePath):
		if self.remoteModified is None:
			# New file, check if it already exists. If so, consider them equal.
			if self.fileExists(remotePath):
				self.updateModified(remotePath, local=False)
			else:
				self.copyToRemote(localPath, remotePath)
			return

		if self.localModified is None:
			self.copyToLocal(localPath, remotePath)
			return

		# Check if deleted
		if not self.fileExists(localPath):
			path = os.path.join(remotePath, self.path, self.filename)
			print("Remove file %s" % path)
			if self.fileExists(remotePath):
				os.remove(path)
			self.removed = True
			return
		elif not self.fileExists(remotePath):
			path = os.path.join(localPath, self.path, self.filename)
			print("Remove file %s" % path)
			if self.fileExists(localPath):
				os.remove(path)
			self.removed = True
			return

		# Check local modification
		if os.path.getmtime(os.path.join(localPath, self.path, self.filename)) != self.localModified:
			hash = self.calculateHash(localPath)
			if self.hash != hash:
				self.copyToRemote(localPath, remotePath)
				self.hash = hash
			# Always update modified so we do not need to rehash it next time
			self.updateModified(localPath, local=True)

		# Check remote modification
		if os.path.getmtime(os.path.join(remotePath, self.path, self.filename)) != self.remoteModified:
			self.copyToLocal(localPath, remotePath)
			self.updateModified(remotePath, local=False)

	def copyToLocal(self, localPath, remotePath):
		lpath = os.path.join(localPath, self.path)
		rpath = os.path.join(remotePath, self.path, self.filename)
		print("Copy %s to %s" % (rpath, lpath))
		if not os.path.exists(lpath):
			os.makedirs(lpath)
		if not self.__doCopy(rpath, os.path.join(lpath, self.filename)):
			return
		self.updateHash(localPath)

	def copyToRemote(self, localPath, remotePath):
		lpath = os.path.join(localPath, self.path, self.filename)
		rpath = os.path.join(remotePath, self.path)
		print("Copy %s to %s" % (lpath, rpath))
		if not os.path.exists(rpath):
			os.makedirs(rpath)
		shutil.copy2(lpath, rpath)
		self.updateModified(remotePath, local=False)

	def updateHash(self, basepath):
		self.hash = self.calculateHash(basepath)
		self.updateModified(basepath, local=True)

	def updateModified(self, basepath, local):
		path = os.path.join(basepath, self.path, self.filename)
		if local:
			self.localModified = os.path.getmtime(path)
		else:
			self.remoteModified = os.path.getmtime(path)

	def __doCopy(self, src, dest):
		srcf = open(src, 'rb')
		destf = open(dest, 'wb')
		srcSize = os.stat(src).st_size

		curBlockPos = 0
		blockSize = 16384
		while True:
			curBlock = srcf.read(blockSize)
			curBlockPos += blockSize
			sys.stdout.write(
				'\r%s/%s - %s%%\r' % (self.__formatSize(curBlockPos), self.__formatSize(srcSize), str(round(float(curBlockPos)/float(srcSize)*100)))
			)
			sys.stdout.flush()
			if not curBlock:
				sys.stdout.write('\n')
				break
			else:
				destf.write(curBlock)
		srcf.close()
		destf.close()
		destSize = os.stat(dest).st_size
		if destSize != srcSize:
			raise IOError(
				"New file-size does not match original (src: %s, dest: %s)" % (
				srcSize, destSize)
			)
		return True

	def __formatSize(self, size):
		suffixes = ['MB', 'KB']
		suffix = 'bytes'
		while size > 1024 and len(suffixes) > 0:
			size = size / 1024
			suffix = suffixes.pop()
		return '%i%s' % (size, suffix)

class PUnison(object):
	def __init__(self):
		self.local = None
		self.remote = None
		self.name = None
		self._files = []

	def run(self):
		try:
			opts, args = getopt.getopt(sys.argv[1:], "", ["local=", "remote=", "name=", "help"])
		except getopt.GetoptError:
			#printUsage()
			sys.exit(2)

		for opt, arg in opts:
			if opt in ("--name"):
				self.name = arg

		if self.name is not None:
			config = ConfigParser.SafeConfigParser()
			config.read(os.path.join(os.environ['HOME'], '.config', 'punison', 'punison.conf'))
			if config.has_option(self.name, 'local'):
				self.local = config.get(self.name, 'local', None)
			if config.has_option(self.name, 'remote'):
				self.remote = config.get(self.name, 'remote', None)

		for opt, arg in opts:
			if opt in ("--local"):
				self.local = arg
			elif opt in ("--remote"):
				self.remote = arg

		if self.name is None:
			print("Parameter --name must be set")
			sys.exit(2)

		if self.local is None or self.remote is None:
			print("Both local and remote path must be set")
			sys.exit(2)

		self.__loadConfig()
		self.__updateFiles(self.local, local=True)
		self.__updateFiles(self.remote, local=False)
		self.__copyFiles()
		self.__saveConfig()

	def __copyFiles(self):
		for f in self._files:
			try:
				f.updateIfNeeded(self.local, self.remote)
			except KeyboardInterrupt:
				print("Aborted while copying files!")
				break
			except Exception as e:
				print("Could not copy file %s/%s: %s" % (str(f.path), str(f.filename), str(e)))
		self._files = [f for f in self._files if not hasattr(f, 'removed') or f.removed == False]

	def __findFile(self, path, filename):
		for f in self._files:
			if f.path == path and f.filename == filename:
				return f
		return None

	def __loadConfig(self):
		try:
			f = open(os.path.join(os.environ['HOME'], '.config', 'punison', self.name + '.pickle'), 'rb')
			self._files = pickle.load(f)
			f.close()
		except:
			pass

	def __saveConfig(self):
		f = open(os.path.join(os.environ['HOME'], '.config', 'punison', self.name + '.pickle'), 'wb')
		pickle.dump(self._files, f, 0)
		f.close()

	def __updateFiles(self, path, local):
		f = []
		foundFiles = []
		for (dirpath, dirnames, filenames) in os.walk(path):
			lpath = os.path.relpath(dirpath, path)
			for filename in filenames:
				f = self.__findFile(lpath, filename)
				foundFiles.append({path: lpath, filename: filename})
				if f is None:
					f = File(lpath, filename)
					if local:
						f.updateHash(path)
					else:
						f.updateModified(path, local=False)
					self._files.append(f)

if __name__ == '__main__':
	p = PUnison()
	p.run()
