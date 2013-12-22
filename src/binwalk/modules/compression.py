#!/usr/bin/env python

import os
import ctypes
import ctypes.util
from binwalk.core.module import Option, Kwarg, Module

class Deflate(object):
	'''
	Finds and extracts raw deflate compression streams.
	'''

	ENABLED = False
	BLOCK_SIZE = 33*1024
	# To prevent many false positives, only show data that decompressed to a reasonable size and didn't just result in a bunch of NULL bytes
	MIN_DECOMP_SIZE = 32*1024
	DESCRIPTION = "Raw deflate compression stream"

	def __init__(self, module):
		self.module = module

		# The tinfl library is built and installed with binwalk
		self.tinfl = ctypes.cdll.LoadLibrary(ctypes.util.find_library("tinfl"))
		if not self.tinfl:
			raise Exception("Failed to load the tinfl library")
		
		# Add an extraction rule
		if self.module.extractor.enabled:
			self.module.extractor.add_rule(regex='^%s' % self.DESCRIPTION.lower(), extension="deflate", cmd=self._extractor)

	def pre_scan(self, fp):
		if self.tinfl:
			# Make sure we'll be getting enough data for a good decompression test
			if fp.block_read_size < self.SIZE:
				fp.set_block_size(peek=self.SIZE)

			self._deflate_scan(fp)

			return PLUGIN_TERMINATE

	def _extractor(self, file_name):
		if self.tinfl:
			out_file = os.path.splitext(file_name)[0]
			self.tinfl.inflate_raw_file(file_name, out_file)

	def decompress(self, data):
		description = None

		decomp_size = self.tinfl.is_deflated(data, len(data), 0)
		if decomp_size >= self.MIN_DECOMP_SIZE:
			description = self.DESCRIPTION + ', uncompressed size >= %d' % decomp_size

		return description

class RawCompression(Module):

	DECOMPRESSORS = {
			'deflate' : Deflate,
	}

	TITLE = 'Raw Compression'

	CLI = [
			Option(short='X',
				   long='deflate',
				   kwargs={'enabled' : True, 'decompressor_class' : 'deflate'},
				   description='Scan for raw deflate compression streams'),
	]

	KWARGS = [
			Kwarg(name='enabled', default=False),
			Kwarg(name='decompressor_class', default=None),
	]

	def init(self):
		self.decompressor = self.DECOMPRESSORS[self.decompressor_class](self)

	def run(self):
		for fp in iter(self.next_file, None):

			fp.set_block_size(peek=self.decompressor.BLOCK_SIZE)

			self.header()

			while True:
				(data, dlen) = fp.read_block()
				if not data:
					break

				for i in range(0, dlen):
					description = self.decompressor.decompress(data[i:i+self.decompressor.BLOCK_SIZE])
					if description:
						self.result(description=description, file=fp, offset=fp.tell()-dlen+i)

				self.status.completed = fp.tell() - fp.offset

			self.footer()
