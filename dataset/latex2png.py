# mostly taken from http://code.google.com/p/latexmath2png/
# install preview.sty
import os
import re
import sys
import io
import tempfile
import subprocess
from PIL import Image


class Latex:
    BASE = r'''
\documentclass[varwidth]{standalone}
\usepackage{fontspec,unicode-math}
\usepackage[active,tightpage,displaymath,textmath]{preview}
\setmathfont{%s}
\begin{document}
\thispagestyle{empty}
%s
\end{document}
'''

    def __init__(self, math, dpi=250):
        '''takes list of math code. `returns each element as PNG with DPI=`dpi`'''
        self.math = math
        self.dpi = dpi

    def write(self, font='Latin Modern Math'):
        # inline = bool(re.match('^\$[^$]*\$$', self.math)) and False
        try:
            workdir = tempfile.gettempdir()
            fd, texfile = tempfile.mkstemp('.tex', 'eq', workdir, True)
            # print(self.BASE % (font, self.math))
            with os.fdopen(fd, 'w+') as f:
                document = self.BASE % (font, '\n'.join(self.math))
                #print(document)
                f.write(document)

            png=self.convert_file(texfile, workdir)
            return png

        finally:
            if os.path.exists(texfile):
                try:
                    os.remove(texfile)
                except PermissionError:
                    pass

    def convert_file(self, infile, workdir):

        try:
            # Generate the PDF file
            cmd='xelatex -halt-on-error -output-directory %s %s' % (workdir, infile)

            p=subprocess.Popen(
                cmd,
                shell = True,
                stdin = subprocess.PIPE,
                stdout = subprocess.PIPE,
                stderr = subprocess.PIPE,
            )
            sout, serr=p.communicate()
            # Something bad happened, abort
            if p.returncode != 0:
                raise Exception('latex error', serr, sout)

            # Convert the PDF file to PNG's
            pdffile=infile.replace('.tex', '.pdf')
            pngfile=os.path.join(workdir, infile.replace('.tex', '.png'))

            cmd='magick convert -density %i -colorspace gray %s -quality 90 %s' % (
                self.dpi,
                pdffile,
                pngfile,
            )  # -bg Transparent -z 9
            p=subprocess.Popen(
                cmd,
                shell = True,
                stdin = subprocess.PIPE,
                stdout = subprocess.PIPE,
                stderr = subprocess.PIPE,
            )

            sout, serr=p.communicate()
            if p.returncode != 0:
                raise Exception('PDFpng error', serr)

            png=[open(pngfile.replace('.png', '')+'-%i.png' % i, 'rb').read() for i in range(len(self.math))]
            return png

        finally:
            # Cleanup temporaries
            basefile=infile.replace('.tex', '')
            tempext='.aux', '.pdf', '.log', '.png'
            for te in tempext:
                tempfile=basefile + te
                if os.path.exists(tempfile):
                    os.remove(tempfile)


__cache={}


def tex2png(eq, **kwargs):
    if not eq in __cache:
        __cache[eq]=Latex(eq, **kwargs).write()
    return __cache[eq]


def tex2pil(tex, **kwargs):
    pngs=Latex(tex, **kwargs).write()
    images=[Image.open(io.BytesIO(d)) for d in pngs]
    return images


if __name__ == '__main__':
    if len(sys.argv) > 1:
        src=sys.argv[1]
    else:
        src=r'\begin{equation}\mathcal{ L}\nonumber\end{equation}'

    print('Equation is: %s' % src)
    print(Latex(src).write())
