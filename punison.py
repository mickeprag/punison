#!/usr/bin/env python

import getopt, hashlib, os, shutil, sys, time
import ConfigParser, pickle

class File(object):
	def __init__(self, path, filename):
		self.path = path
		self.filename = filename
		self.localModified = None
		self.remoteModified = None
		self.hash = None
		self.removed = False
		self.partial = False

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

	def updateIfNeeded(self, localPath, remotePath, minimumFreeSpace):
		if self.remoteModified is None:
			# New file, check if it already exists. If so, consider them equal.
			if self.fileExists(remotePath):
				if self.partial == False:
					self.updateModified(remotePath, local=False)
					return
				print("File exists on both places but is marked partial. Copy again")
			self.copyToRemote(localPath, remotePath, minimumFreeSpace)
			return

		if self.localModified is None:
			self.copyToLocal(localPath, remotePath, minimumFreeSpace)
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
				self.copyToRemote(localPath, remotePath, minimumFreeSpace)
				self.hash = hash
			# Always update modified so we do not need to rehash it next time
			self.updateModified(localPath, local=True)

		# Check remote modification
		if os.path.getmtime(os.path.join(remotePath, self.path, self.filename)) != self.remoteModified:
			self.copyToLocal(localPath, remotePath, minimumFreeSpace)
			self.updateModified(remotePath, local=False)

	def copyToLocal(self, localPath, remotePath, minimumFreeSpace):
		self.partial = True
		lpath = os.path.join(localPath, self.path)
		rpath = os.path.join(remotePath, self.path, self.filename)
		print("Copy %s to %s" % (rpath, lpath))
		if not os.path.exists(rpath):
			print("remote file is already removed")
			self.removed = True
			return
		if not os.path.exists(lpath):
			os.makedirs(lpath)
		if not self.__doCopy(rpath, os.path.join(lpath, self.filename), minimumFreeSpace):
			return
		self.updateHash(localPath)
		self.partial = False

	def copyToRemote(self, localPath, remotePath, minimumFreeSpace):
		lpath = os.path.join(localPath, self.path, self.filename)
		rpath = os.path.join(remotePath, self.path)
		print("Copy %s to %s" % (lpath, rpath))
		if not os.path.exists(lpath):
			print("local file is already removed")
			self.removed = True
			return
		if not os.path.exists(rpath):
			os.makedirs(rpath)
		self.partial = True
		if not self.__doCopy(lpath, os.path.join(rpath, self.filename), minimumFreeSpace):
			return
		self.updateModified(remotePath, local=False)
		self.partial = False

	def updateHash(self, basepath):
		self.hash = self.calculateHash(basepath)
		self.updateModified(basepath, local=True)

	def updateModified(self, basepath, local):
		path = os.path.join(basepath, self.path, self.filename)
		if local:
			self.localModified = os.path.getmtime(path)
		else:
			self.remoteModified = os.path.getmtime(path)

	def __doCopy(self, src, dest, minimumFreeSpace):
		s = os.statvfs(os.path.dirname(dest))
		freeSpace = s.f_frsize * s.f_bavail
		srcf = open(src, 'rb')
		srcSize = os.stat(src).st_size
		minimumFreeSpace = minimumFreeSpace * 1024 * 1024 # Convert to MB
		if freeSpace < (srcSize + minimumFreeSpace):
			print("Not enough free space on target device. Need %s, have %s" % (self.__formatSize(srcSize+minimumFreeSpace), self.__formatSize(freeSpace)))
			return False
		destf = open(dest, 'wb')
		startTime = time.time()

		curBlockPos = 0
		blockSize = 16384
		lastBlockStartTime = startTime
		percentDone = -1
		while True:
			curBlock = srcf.read(blockSize)
			curBlockPos += blockSize
			if not curBlock:
				sys.stdout.write('\n')
				break
			else:
				destf.write(curBlock)
			t = time.time()
			avgSpeed = curBlockPos / (t-startTime)
			lastBlockSpeed = blockSize / (t-lastBlockStartTime)
			lastBlockStartTime = time.time()
			secondsLeft = (srcSize - curBlockPos) / avgSpeed
			p = round(float(curBlockPos)/float(srcSize)*100)
			if percentDone != p:
				percentDone = p
				sys.stdout.write(
					'%s/%s - %s%% - %s/s (avg %s/s) %s   \r' % (
						self.__formatSize(curBlockPos),
						self.__formatSize(srcSize),
						str(round(float(curBlockPos)/float(srcSize)*100)),
						self.__formatSize(lastBlockSpeed, bytes=False),
						self.__formatSize(avgSpeed, bytes=False),
						self.__formatTime(secondsLeft)
					)
				)
				sys.stdout.flush()
		srcf.close()
		destf.close()
		destSize = os.stat(dest).st_size
		if destSize != srcSize:
			raise IOError(
				"New file-size does not match original (src: %s, dest: %s)" % (
				srcSize, destSize)
			)
		return True

	def __formatSize(self, size, bytes = True):
		if bytes:
			suffixes = ['MB', 'KB']
			suffix = 'bytes'
		else:
			suffixes = ['Mb', 'Kb']
			suffix = 'bits'
			size = size * 8
		while size > 1024 and len(suffixes) > 0:
			size = size / 1024
			suffix = suffixes.pop()
		return '%i%s' % (size, suffix)

	def __formatTime(self, seconds):
		if seconds < 60:
			return '%i' % seconds
		minutes = seconds // 60
		seconds = seconds % 60
		if minutes < 60:
			return '%02i:%02i' % (minutes, seconds)
		hours = minutes // 60
		minutes = minutes % 60
		return '%02i:%02i:%02i' % (hours, minutes, seconds)

class PUnison(object):
	def __init__(self):
		self.local = None
		self.remote = None
		self.minimumFreeSpace = 0
		self.name = None
		self._files = []

	def run(self):
		try:
			opts, args = getopt.getopt(sys.argv[1:], "", ["local=", "remote=", "name=", "minimumFreeSpace=", "help"])
		except getopt.GetoptError as e:
			print(e)
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
			if config.has_option(self.name, 'minimumFreeSpace'):
				self.minimumFreeSpace = int(config.get(self.name, 'minimumFreeSpace', 0))

		for opt, arg in opts:
			if opt in ("--local"):
				self.local = arg
			elif opt in ("--remote"):
				self.remote = arg
			elif opt in ("--minimumFreeSpace"):
				self.minimumFreeSpace = int(arg)

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
				f.updateIfNeeded(self.local, self.remote, minimumFreeSpace=self.minimumFreeSpace)
			except KeyboardInterrupt:
				print("Aborted while copying files!")
				break
			except Exception as e:
				print("Could not copy file %s/%s: %s" % (str(f.path), str(f.filename), str(e)))
				break
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
