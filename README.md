# tex2pix - LaTeX OCR
The goal of this project is to create a learning based system that takes an image of a math formula and returns corresponding LaTeX code

## Data
We need paired data for the network to learn. Luckly there is a lot of LaTeX code on the internet, e.g. [wikipedia](www.wikipedia.org), [arXiv](www.arxiv.org). We also use the formulae from the [im2latex-100k](https://zenodo.org/record/56198#.V2px0jXT6eA) dataset.

### Fonts
* Latin Modern Math
* GFSNeohellenicMath.otf
* Asana Math
* XITS Math

## Requirements
### Dataset
In order to render the math in many different fonts we use  XeLaTeX, generate a PDF and finally convert it to a PNG. For the last step we need to use some third party tools: 
* [XeLaTeX](https://www.ctan.org/pkg/xetex)
* [ImageMagick](https://imagemagick.org/) with [Ghostscript](https://www.ghostscript.com/index.html).
* [Node.js](https://nodejs.org/) to run [KaTeX](https://github.com/KaTeX/KaTeX)
* [`de-macro`](https://www.ctan.org/pkg/de-macro) >= 1.4
* Python 3.7+ & dependencies


## Contribution
Contributions of any kind are welcome.

## Acknowledgement
Code taken and modified from [im2markup](https://github.com/harvardnlp/im2markup), [arxiv_leaks](https://github.com/soskek/arxiv_leaks)
