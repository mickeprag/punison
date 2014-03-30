punison
===================

A simple two way file synchronizer written in Python. This project is inspired by Unison but offers some differences.

- PUnison only needs to be installed and run on one of the computers. This makes it easier to syncronize with embedded devices.
- PUnison detects file changes using hash for local files and size+modification date for remote files
- PUnison is written in Python to make it easily portable to different platforms

usage
===================

punison --name [name] --local [local path] --remote [remote path]

--name: This is a unique name for each syncronization. PUnison uses this name to store files copied  
--local: The local files. This path must be on the same computer since PUnison will read and hash the file contents  
--remote: The path to the remote files. This can be a slow network drive and PUnison will try to keep read and writes to a minimum

example:  
punison --name movies --local /home/micke/Documents/movies --remote /mnt/phone/Documents/movies

configuration files
===================

It is possible to skip the local and remote parameter by storing these in a configuration file

example:  
Put this in ~/.config/punison/punison.conf:

```
[movies]
local = /home/micke/Documents/movies
remote = /mnt/phone/Documents/movies
```

You can now run PUnison:  
punison --name movies
