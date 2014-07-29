svg2latex
=========

Producing diagrams for incorporation into LaTeX documents is...
difficult.  There are many partial solutions, and this is mine.

Basic Use
---------

This tool is not standalone, and has been written only to fit into my
own workflow.  It places a heavy burden on the user.

  1. Install the [textext](http://pav.iki.fi/software/textext/) Inkscape
     extension.
  3. Create a figure.  Use textext for any text you want to include.
     You should be able to place the text in the correct location in
     Inkscape, and expect it to appear in the same place in the final
     output.  (Note: currently, transforming the textext element with
     anything other than a translation is not supported).
  4. Save the file (as an Inkscape SVG).
  5. Run svg2latex on the file to produce a PDF and a LaTeX file.
  6. In your document, use the \input command to include the LaTeX file
     (you don't need to directly include the PDF file; it's referenced
     from the LaTeX file).

If you want to use non-textext text in your figure, then:

  1. Install the [cm-unicode](http://cm-unicode.sourceforge.net/)
     fonts, and use them in your document.
  2. Be careful about text size -- if you want to adjust the size of
     text, use the font size, don't just scale the text element.
  3. Be careful about text alignment -- svg2latex should respect the
     left/center/right alignment setting of text, so if you need things
     to line up along an edge or line up with a connecting arrow, then
     you should be careful to choose the appropriate text alignment.
     If you have the correct alignment, then you should be able to edit
     the text without it moving to a stupid position.
  4. Be careful about text size and space.  The final rendered output
     won't be exactly the same size as what you see in Inkscape, so
     you'll need to check the output and make adjustments.
  5. You can rotate normal text elements, and they should be correctly
     rotated in the final output.

You can have both textext elements and normal SVG text in the same
document, and they will all be extracted (put into the LaTeX output and
excluded from the PDF output).  Unfortunately, textext output is scaled,
so the font sizes won't match normal SVG text.

To Do
-----

  * Add some kind of support for rotations and scaling of textext text.
  * Use a proper matrix decomposition on the accumulated transform
    matrix (or at least the top left 2x2 corner of it) to determine
    scale factor(s) and rotation angle.  This should allow more
    strangely transformed text (e.g., skewed text) to be supported.
  * Investigate an alternate approach, which is to render the textext
    elements separately (so that they are rendered in the same context
    used by textext itself) and then perform some kind of PDF merge
    operation to combine them with the (text-free) PDF exported by
    Inkscape.

Why I made this tool
--------------------

I create my diagrams in Inkscape.  Inkscape is pretty bad, but it's
still nicer to use than xfig, and it's nicer (for me, for some tasks)
than creating diagrams in text using tikz.

Inkscape includes various export methods, one of which is PDF+LaTeX.
When you export to PDF, there is a checkbox you can tick to tell it to
exclude text from the PDF and create a matching tex file that uses a
LaTeX picture environment to embed the PDF (with \includegraphics) and
overlay nice LaTeX-typeset text.

Unfortunately, if you're using Inkscape's PDF+LaTeX export, then you
can't see at design time how the text is going to be typeset.  For some
placements this doesn't matter, because you can still get the text's
anchor point into the right position quite easily and a bit of stretch
or shrink in the final output compared to what you see in Inkscape is
not a big deal.  However, if your text includes a lot of mathematical
notation (even including lone references to variables, which I find is
quite common when I'm putting labels on things), then the text you see
in Inkscape will be very different from the final rendered text, because
the text in Inkscape will have (La)TeX math-mode code in it.  This makes
it harder than it should be to lay out the figure neatly, because a) you
don't know how big your text is going to be, and b) all the math mode
stuff gets in the way and often extends over other parts of your figure
because it's significantly longer than the actual typeset maths.

But then I found an Inkscape extension called textext:

    [textext](http://pav.iki.fi/software/textext/) ([textext on bitbucket](https://bitbucket.org/pv/textext))

textext approaches the problem from the opposite direction.  Instead of
taking Inkscape text and turning it into LaTeX code to be typset, it
takes LaTeX code and renders it with pdflatex, immediately embedding the
result back into your Inkscape document (and retaining the original
LaTeX code in a custom attribute so that you can edit it).

This is *fantastic*, because instead of seeing your LaTeX code in the
Inkscape window, you see the exact correct rendered LaTeX output, and
you can move it around and place it as a block.  The LaTeX code itself is
edited through a simple dialog window created by the extension.

But... although it's great when you're creating the figure, it's still
not good for the final *final* PDF output, because the conversion from
LaTeX to PDF to SVG (Inkscape) and then (presumably) back to PDF to be
embedded into a LaTeX document as a figure means that the text is no
longer treated as text, but instead decays into plain old filled
outline shapes, which are meaningless as far as the computer or a PDF
viewing application is concerned.  I would imagine that process also
results in an increase in data size and probably also a reduction in
rendering efficiency, but I don't know for sure.

My solution is to add yet another step to the process, which is to make
a custom SVG to PDF+LaTeX converter.  This does the same job as the
built in Inkscape PDF+LaTeX export method, but is extended so that it
understands the custom attributes used by the textext extension.

The result is that both normal Inkscape text, *and* rendered LaTeX text
that has been embedded using textext are excluded from the PDF part and
included in the LaTeX picture environment part.  Those parts will then
all be re-rendered by LaTeX when the two pieces are combined during
final document rendering.  This means that *all* the text is kept in
text form in the PDF, so it can be selected and copied and so on.

What's more, since LaTeX's typesetting is (reasonably) stable, the
rendered text that you see in Inkscape matches extremely closely with
the final output, which means that you can properly design and lay out
your figures in Inkscape!
