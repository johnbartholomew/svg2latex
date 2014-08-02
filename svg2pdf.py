#!/usr/bin/env python3
# vim: set ts=4 sw=4 noet ai:

import lxml.etree as etree
import subprocess
import tempfile
import textwrap
import argparse
import string
import codecs
import shutil
import math
import re
import io
import os
import sys

SVG_UNITS_TO_BIG_POINTS = 72.0/90.0
INKSCAPE_DPI = 90.0

UNIT_SCALE_TO_USER_UNITS = {
	'': 1.0,
	'px': 1.0,  # user units are defined to be equal to 'px'
	'in': INKSCAPE_DPI,
	'cm': INKSCAPE_DPI / 2.54, # 1 inch = 2.54 cm
	'mm': INKSCAPE_DPI / 25.4, # 1 inch = 25.4 mm
	'pt': INKSCAPE_DPI / 72.0, # 1 inch = 72 pt
	'pc': INKSCAPE_DPI * 12.0 / 72.0 # 1 pica = 12 pt
}

NS_TEXTEXT = r"http://www.iki.fi/pav/software/textext/"
SVG_NSS = {
   'dc': r"http://purl.org/dc/elements/1.1/",
   'cc': r"http://creativecommons.org/ns#",
   'rdf': r"http://www.w3.org/1999/02/22-rdf-syntax-ns#",
   'svg': r"http://www.w3.org/2000/svg",
   'textext': NS_TEXTEXT,
   'xlink': r"http://www.w3.org/1999/xlink",
   'sodipodi': r"http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
   'inkscape': r"http://www.inkscape.org/namespaces/inkscape",
}

def ns_attrib(attrib):
	ns, _, attrib = attrib.partition(':')
	return '{' + SVG_NSS[ns] + '}' + attrib

class AffineTransform:
	def __init__(s, t=None, m=None):
		s.t = (0.0, 0.0) if t is None else t
		s.m = (1.0,0.0, 0.0,1.0) if m is None else m

	def clone(s):
		nt = AffineTransform()
		nt.t = s.t
		nt.m = s.m
		return nt

	def translate(s, tx, ty):
		s.matrix(1.0,0.0, 0.0,1.0, tx,ty)

	def rotate_degrees(s, angle, cx=0.0, cy=0.0):
		angle = math.radians(angle)
		sin,cos = math.sin(angle), math.cos(angle)
		if cx != 0.0 or cy != 0.0:
			s.translate(cx,cy)
			s.matrix(cos,sin, -sin,cos, 0.0,0.0)
			s.translate(-cx,-cy)
		else:
			s.matrix(cos,sin, -sin,cos, 0.0,0.0)

	def scale(s, sx, sy=None):
		if sy is None:
			sy = sx
		s.matrix(sx,0.0, 0.0,sy)

	def matrix(s, a,b,c,d,e=0.0,f=0.0):
		sa,sb,sc,sd = s.m
		se,sf = s.t

		ma = sa*a + sc*b
		mb = sb*a + sd*b
		mc = sa*c + sc*d
		md = sb*c + sd*d
		me = sa*e + sc*f + se
		mf = sb*e + sd*f + sf
		s.m = (ma,mb, mc,md)
		s.t = (me,mf)

	def applyTo(s, x, y=None):
		if y is None:
			x,y = x
		xx = s.t[0] + s.m[0]*x+s.m[2]*y
		yy = s.t[1] + s.m[1]*x+s.m[3]*y
		return (xx,yy)

	def __str__(s):
		return '[{},{},{}  ;  {},{},{}]'.format(s.m[0],s.m[2],s.t[0],s.m[1],s.m[3],s.t[1])

	def __mul__(a, b):
		a11,a21,a12,a22 = a.m
		a13,a23 = a.t
		b11,b21,b12,b22 = b.m
		b13,b23 = b.t

		# cIJ = aI1*b1J + aI2*b2J + aI3*b3J
		c11 = a11*b11 + a12*b21
		c12 = a11*b12 + a12*b22
		c13 = a11*b13 + a12*b23 + a13
		c21 = a21*b11 + a22*b21
		c22 = a21*b12 + a22*b22
		c23 = a21*b13 + a22*b23 + a23
		return AffineTransform((c13,c23), (c11,c21,c12,c22))

	def get_rotation(s):
		m11,m21,m12,m22 = s.m
		len1 = math.sqrt(m11*m11 + m21*m21)
		len2 = math.sqrt(m12*m12 + m22*m22)
		# TODO check that len1 and len2 are close to 1
		# TODO check that the matrix is orthogonal
		# TODO do a real matrix decomposition here!
		return math.degrees(math.atan2(m21,m11))

RX_TRANSFORM = re.compile(r'^\s*(\w+)\(([0-9,\s\.Ee+-]*)\)\s*$')

def svg_parse_transform(attribute):
	m = RX_TRANSFORM.match(attribute)
	if m is None:
		raise Exception('bad transform (' + attribute + ')')
	func = m.group(1)
	args = [float(x.strip()) for x in m.group(2).replace(',',' ').split()]
	xform = AffineTransform()
	if func == 'matrix':
		if len(args) != 6:
			raise Exception('bad matrix transform')
		xform.matrix(*args)
	elif func == 'translate':
		if len(args) < 1 or len(args) > 2:
			raise Exception('bad translate transform')
		tx = args[0]
		ty = args[1] if len(args) > 1 else 0.0
		xform.translate(tx,ty)
	elif func == 'scale':
		if len(args) < 1 or len(args) > 2:
			raise Exception('bad scale transform')
		sx = args[0]
		sy = args[1] if len(args) > 1 else sx
		xform.scale(sx,sy)
	else:
		raise Exception('unsupported transform attribute (' + attribute + ')')
	return xform

def svg_split_style(style):
	parts = [x.strip() for x in style.split(';')]
	parts = [x.partition(':') for x in parts if x != '']
	st = {}
	for p in parts:
		st[p[0].strip()] = p[2].strip()
	return st

def svg_parse_color(col):
	if col[0] == '#':
		r = int(col[1:3], 16)
		g = int(col[3:5], 16)
		b = int(col[5:7], 16)
		return (r,g,b)
	else:
		raise Exception('only hash-code colors are supported!')

def svg_find_accumulated_transform(el):
	xform = AffineTransform()
	while el is not None:
		if 'transform' in el.attrib:
			t = svg_parse_transform(el.attrib['transform'])
			xform = t * xform
		el = el.getparent()
	return xform

RX_LENGTH = re.compile(r'''
    \s*
	    (?P<value>
		[+-]?                                # optional sign
		(?: [0-9]+ \.? | \. [0-9] ) [0-9]*   # integer ([0-9]+) or float ([0-9]*\.[0-9]+) mantissa
		(?: e [+-]? [0-9]+)?                 # optional exponent
		) # P<value>
		(?P<unit>  em|ex | px|in|cm|mm|pt|pc | [%])?
    \s*''', re.VERBOSE | re.IGNORECASE)
def svg_parse_length(text, apply_unit=True):
	m = RX_LENGTH.match(text)
	if m is not None:
		raw_value = float(m.group('value'))
		unit = m.group('unit')
		if apply_unit:
			return UNIT_SCALE_TO_USER_UNITS[unit] if unit is not None else raw_value
		else:
			return raw_value, unit
	else:
		raise Exception('invalid length "{}"'.format(text))

def get_lines_from_tspans(textnode):
	lines = []
	for el in textnode.xpath('./svg:tspan[@sodipodi:role="line"]', namespaces=SVG_NSS):
		lines.append(el.text)
	return lines

TEX_WRAPPER_HEAD = string.Template(r'''\documentclass{standalone}
\usepackage{varwidth}
\usepackage{graphicx}
\usepackage{color}
\usepackage{rotating}
$extra_preamble
\begin{document}%
\setlength{\unitlength}{0.8bp}%
\begingroup%
\begin{picture}($picture_width,$picture_height)%
''')
TEX_WRAPPER_BG = string.Template('\put(0,0){\includegraphics{$background_path}}')
TEX_WRAPPER_NODE = string.Template(r'\put($x,$y){$texcode}')
TEX_WRAPPER_TAIL = string.Template(r'''\end{picture}%
\endgroup%
\end{document}
''')

class TeXPicture:
	def __init__(self):
		self.width = 0.0
		self.height = 0.0
		self.nodes = []
		self.extra_preamble = ''

	def emit_standalone(self, out, background=None):
		out.write(TEX_WRAPPER_HEAD.substitute(
			extra_preamble=self.extra_preamble,
			picture_width=self.width,
			picture_height=self.height))
		if background is not None:
			out.write(TEX_WRAPPER_BG.substitute(background_path=background))
			out.write('%\n')
		for node in self.nodes:
			out.write(node.to_tex())
			out.write('%\n')
		out.write(TEX_WRAPPER_TAIL.substitute())

class TeXPictureElement:
	def __init__(self):
		self.tex_pos = (0.0, 0.0)
		self.texcode = ''

	def to_tex(self):
		return TEX_WRAPPER_NODE.substitute(
				x=self.tex_pos[0], y=self.tex_pos[1], texcode=self.texcode)

def convert_tspans_to_tex(text_node):
	# TODO make this much more comprehensive in understanding SVG text and styling
	lines = get_lines_from_tspans(text_node)
	if len(lines) > 1:
		return r'\shortstack{' + r'\\'.join(lines) + '}'
	else:
		return lines[0]

def decode_escaped_string(text, encoding='utf-8'):
	return codecs.escape_decode(text)[0].decode(encoding)

def extract_text_to_texpic(svgroot):
	pic = TeXPicture()
	pic.width = svg_parse_length(svgroot.attrib['width'])
	pic.height = svg_parse_length(svgroot.attrib['height'])

	wrapper = textwrap.TextWrapper()
	wrapper.expand_tabs = True
	wrapper.width = 120
	wrapper.initial_indent = '   '
	wrapper.subsequent_indent = '   '

	# attempt to convert normal SVG text
	for el in svgroot.xpath('//svg:text', namespaces=SVG_NSS):
		node = TeXPictureElement()
		node.xform = svg_find_accumulated_transform(el)
		x = svg_parse_length(el.attrib.get('x','0'))
		y = svg_parse_length(el.attrib.get('y','0'))
		node.svg_pos = (x,y)
		x,y = node.xform.applyTo(x,y)
		node.tex_pos = (x, pic.height - y)
		# TODO re-enable this!
		#node.texcode = convert_tspans_to_tex(el)
		#pic.nodes.append(node)
		el.getparent().remove(el)

	preamble_files = set()

	# extract textext nodes
	for el in svgroot.xpath('//*[@textext:text]', namespaces=SVG_NSS):
		node = TeXPictureElement()
		textext = decode_escaped_string(el.attrib[ns_attrib('textext:text')])
		preamble_src = decode_escaped_string(el.attrib[ns_attrib('textext:preamble')])
		preamble_files.add(preamble_src)
		node.texcode = (
				'\\makebox(0,0)[lt]{\\begin{varwidth}{20in}%\n' +
				textext +
				'%\n\\relax\\end{varwidth}}')
		node.xform = svg_find_accumulated_transform(el)
		node.svg_pos = (0,0)
		x,y = node.xform.t
		node.tex_pos = (x, pic.height - y)
		pic.nodes.append(node)
		el.getparent().remove(el)

	preamble = []
	for path in preamble_files:
		print('preamble from:', preamble_src)
		with open(path, 'r', encoding='utf-8') as fl:
			preamble.extend(fl.readlines())

	pic.extra_preamble = ''.join(preamble)
	print('extra premable:')
	print(pic.extra_preamble)

	return pic

class WorkingDirectory:
	def __init__(self, new_dir):
		self._new_dir = new_dir
		self._cwd = None

	def __enter__(self):
		self._cwd = os.getcwd()
		os.chdir(self._new_dir)
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		os.chdir(self._cwd)

def generate_pdf_from_svg(svgdata, svgname, pdfname, base_dir=None):
	svgpath = os.path.abspath(svgname)
	pdfpath = os.path.abspath(pdfname)
	cmd = ['/usr/bin/inkscape',
	       '--without-gui',
	       '--export-area-page',
	       '--export-pdf={}'.format(pdfpath),
	       svgpath]
	with open(svgpath, 'wb') as svgfile:
		svgdata.write(svgfile, encoding='utf-8', xml_declaration=True)
	with WorkingDirectory(base_dir):
		print('cwd for inkscape:', os.getcwd())
		print('inkscape command:', ' '.join(cmd))
		subprocess.check_call(cmd, stdin=subprocess.DEVNULL)

def execute_latex(texname, command='pdflatex'):
	cmd = ['/usr/bin/' + command,
	       '-interaction=batchmode',
	       '-halt-on-error',
	       '-file-line-error',
	       texname]
	subprocess.check_call(cmd, stdin=subprocess.DEVNULL)

def main():
	parser = argparse.ArgumentParser(description='Convert an SVG containing LaTeX elements into a PDF')
	parser.add_argument('-o', '--output', dest='outpath')
	parser.add_argument('inpath', metavar='INPUT')
	args = parser.parse_args()

	basename, _ = os.path.splitext(args.inpath)
	inpath = args.inpath
	outpath = args.outpath if args.outpath is not None else basename + '.pdf'

	xmldoc = etree.parse(args.inpath)
	texpic = extract_text_to_texpic(xmldoc.getroot())

	svgdir = os.path.abspath(os.path.dirname(inpath))

	with tempfile.TemporaryDirectory(prefix='svg2pdf') as working_dir:
		with WorkingDirectory(working_dir):
			generate_pdf_from_svg(xmldoc, 'graphic_only.svg', 'graphic_only.pdf', base_dir=svgdir)
			with open('tex_wrapper.tex', mode='w', encoding='utf-8') as texfile:
				texpic.emit_standalone(texfile, background='graphic_only.pdf')
			execute_latex('tex_wrapper.tex')
		shutil.move(os.path.join(working_dir, 'tex_wrapper.pdf'), outpath)

if __name__ == '__main__':
	main()
