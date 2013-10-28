import getopt, hashlib, os, shutil, sys
import pickle

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

	def updateIfNeeded(self, localPath, remotePath):
		if self.remoteModified is None:
			self.copyToRemote(localPath, remotePath)
			return

		if self.localModified is None:
			self.copyToLocal(localPath, remotePath)
			return

		# Check if deleted
		if not os.path.exists(os.path.join(localPath, self.path, self.filename)):
			print("Removed locally")
			os.remove(os.path.join(remotePath, self.path, self.filename))
			self.removed = True
			return
		elif not os.path.exists(os.path.join(remotePath, self.path, self.filename)):
			print("Removed remote")
			os.remove(os.path.join(localPath, self.path, self.filename))
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
			print("  File is modified remote")
			self.copyToLocal(localPath, remotePath)
			self.updateModified(remotePath, local=False)

	def copyToLocal(self, localPath, remotePath):
		print("  Copy file to local")
		lpath = os.path.join(localPath, self.path)
		rpath = os.path.join(remotePath, self.path, self.filename)
		if not os.path.exists(lpath):
			os.makedirs(lpath)
		shutil.copy2(rpath, lpath)
		self.updateHash(localPath)

	def copyToRemote(self, localPath, remotePath):
		print("  Copy file to remote")
		lpath = os.path.join(localPath, self.path, self.filename)
		rpath = os.path.join(remotePath, self.path)
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

class PUnison(object):
	def __init__(self):
		self.local = None
		self.remote = None
		self._files = []

	def run(self):
		try:
			opts, args = getopt.getopt(sys.argv[1:], "", ["local=", "remote=", "help"])
		except getopt.GetoptError:
			#printUsage()
			sys.exit(2)

		for opt, arg in opts:
			if opt in ("--local"):
				self.local = arg
			elif opt in ("--remote"):
				self.remote = arg

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
			f = open('data.pickle', 'rb')
			self._files = pickle.load(f)
			f.close()
		except:
			pass

	def __saveConfig(self):
		f = open('data.pickle', 'wb')
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