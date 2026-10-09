Cobalt Wrapper v0.3.2

Minecraft 26.3 should now start.

The v0.3.1 shader dump was meant to find this and did. The driver was never
rejecting the shader it was given:

    ERROR: 0:224: '_uniform' : undeclared identifier
    ERROR: 0:224: '_instance_00_00' : Syntax error

`_uniform` and `_instance_00_00` are not in Minecraft's source. They are what
Cobalt wrote.

What was wrong

26.3 is the only version that ships RenderPearl, which flattens uniforms into
interface blocks named `_uniform_00_00` and `_uniform_instance_00_00`. Every
uniform in every 26.3 shader is one of those, and each identifier *starts* with
the word `uniform`.

Cobalt's GLSL post-processor looked for that word as a bare substring rather than
as a keyword, so it fired in the middle of those identifiers. When it did it
consumed the enclosing condition and every statement up to the next `;`, and
rewrote them as a uniform declaration:

    if (_uniform_instance_00_00.UseRgss == 1)
    {
        highp vec2 param = _interface_variable_03;

arrived at the driver as

    if (_uniform _instance_00_00 ;

That dangling underscore is the "undeclared identifier". All 12 core/terrain
pipelines failed; nothing else was wrong.

The same pass had a second defect: it found the end of an interface block at the
block's first `;`, which is inside the body. Blocks containing an initialiser lost
their body and left an unbalanced brace behind. Older versions never hit it, which
is why 1.13 through 26.2 were fine.

Why it took this long

Four earlier attempts to diagnose this failed, each because it guessed at a cause
and tested the guess rather than the code. The dump settled it: comparing the two
sources showed the corruption was already visible in Cobalt's own output. The fix
took twenty minutes after that.

The lasting change is a test. The translation passes are plain string handling, so
`tools/test-glsl.sh` now lifts them out of the shipped source and runs them on a
desktop in seconds. Two of the cases are taken from your failing shaders, and each
must come back byte-identical. Linked against unfixed upstream it fails nine
assertions. It runs in CI, so this class of bug cannot come back unnoticed.

Please uninstall v0.3.0 or v0.3.1 first -- each build signs with a new key, so
Android will refuse to upgrade over them.

Unchanged: same renderer core, same 256 exported names, same 6.1 MB per ABI.