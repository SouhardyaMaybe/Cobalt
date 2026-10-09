// Host-side regression test for the GLSL -> GLSL ES post-processing passes in
// gl/glsl/glsl_for_es.cpp. Compiles the function lifted from the shipped source,
// so it tests the file that actually builds rather than a copy of it.
//
// The whole file pulls in glslang and SPIRV-Cross and cannot be built on a desktop
// machine, but the passes themselves are plain std::string work and that is exactly
// where the Minecraft 26.3 failure lives.

#include <cctype>
#include <cstdio>
#include <string>
#include <vector>

#include "passes.inc"

namespace {

int failures = 0;

void check(bool ok, const std::string& what) {
    std::printf("%s  %s\n", ok ? "ok  " : "FAIL", what.c_str());
    if (!ok) ++failures;
}

void check_contains(const std::string& haystack, const std::string& needle, const std::string& what) {
    const bool ok = haystack.find(needle) != std::string::npos;
    std::printf("%s  %s\n", ok ? "ok  " : "FAIL", what.c_str());
    if (!ok) {
        std::printf("        expected to find: %s\n", needle.c_str());
        ++failures;
    }
}

void check_lacks(const std::string& haystack, const std::string& needle, const std::string& what) {
    const bool ok = haystack.find(needle) == std::string::npos;
    std::printf("%s  %s\n", ok ? "ok  " : "FAIL", what.c_str());
    if (!ok) {
        std::printf("        expected NOT to find: %s\n", needle.c_str());
        ++failures;
    }
}

// What SPIRV-Cross hands to the post-processing passes for a Minecraft 26.3
// `core/terrain` fragment shader, abridged to the head of main() and the two
// uniforms that carry the failure. On a version this shader loads, so the pass
// must leave it completely alone.
const char* mc263_preimage = R"(#version 320 es
precision highp float;
precision highp int;

layout( std140) uniform _uniform_00_01
{
    highp mat4 ProjMat;
} _uniform_instance_00_01;

uniform highp sampler2D _uniform_00_04;
uniform highp sampler2D _uniform_00_05;

void main()
{
    highp vec4 _RESERVED_IDENTIFIER_FIXUP_549 = vec4(0.0);
    if (_uniform_instance_00_00.UseRgss == 1)
    {
        highp vec2 param = _interface_variable_03;
        highp vec2 param_1 = vec2(1.0) / vec2(_uniform_instance_00_02.TextureSize);
        highp vec2 param_2 = param;
        highp vec2 param_3 = param_1;
        _RESERVED_IDENTIFIER_FIXUP_549 = sampleRGSS(_uniform_00_05, param_2, param_3);
    }
    else
    {
        highp vec2 param_2_1 = _interface_variable_03;
        highp vec2 param_3_1 = vec2(1.0) / vec2(_uniform_instance_00_02.TextureSize);
        highp vec2 param_4 = param_2_1;
        highp vec2 param_5 = param_3_1;
        _RESERVED_IDENTIFIER_FIXUP_549 = sampleNearest(_uniform_00_05, param_4, param_5);
    }
}
)";

// The other shape the failure took, from `core/solid_terrain` -- the fog path, which
// is the majority of the failing shaders. Same corruption point, more uniform reads
// after it.
const char* mc263_fog_preimage = R"(#version 320 es
precision highp float;
precision highp int;

layout( std140) uniform _uniform_00_04
{
    highp vec4 FogColor;
    highp float FogEnvironmentalStart;
} _uniform_instance_00_04;

layout( std140) uniform _uniform_00_00
{
    ivec3 CameraBlockPos;
    int UseRgss;
} _uniform_instance_00_00;

layout( std140) uniform _uniform_00_03
{
    highp mat4 ModelViewMat;
    ivec2 TextureSize;
} _uniform_instance_00_03;

uniform highp sampler2D _uniform_00_06;

in highp float _interface_variable_00;
in highp vec2 _interface_variable_03;
layout(location = 0) out highp vec4 _frag_output_00;

highp vec4 calculateFinalColor(highp vec4 color)
{
    highp vec4 fogColor = _uniform_instance_00_04.FogColor;
    return fogColor;
}

void main()
{
    highp vec4 _RESERVED_IDENTIFIER_FIXUP_418 = vec4(0.0);
    if (_uniform_instance_00_01.UseRgss == 1)
    {
        highp vec2 param = _interface_variable_03;
        highp vec2 param_1 = vec2(1.0) / vec2(_uniform_instance_00_03.TextureSize);
        _RESERVED_IDENTIFIER_FIXUP_418 = sampleRGSS(_uniform_00_06, param, param_1);
    }
    highp vec4 color = _RESERVED_IDENTIFIER_FIXUP_418 * _interface_variable_02;
    color = mix(_uniform_instance_00_04.FogColor * vec4(1.0, 1.0, 1.0, color.w), color, vec4(1.0));
    highp vec4 param_4 = color;
    _frag_output_00 = calculateFinalColor(param_4);
}
)";

// The text the driver rejected, exactly as it came off the device: the condition,
// the brace and the first statement were consumed and replaced by a declaration,
// leaving a dangling `_` in front of it.
const char* mc263_damage = "if (_uniform _instance_00_00 ;";

void test_minecraft_263_is_untouched() {
    std::printf("\n-- Minecraft 26.3 core/terrain fragment shader --\n");
    const std::string out = process_uniform_declarations(mc263_preimage);

    check_lacks(out, mc263_damage, "an identifier starting with _uniform is not a keyword");
    check_contains(out, "if (_uniform_instance_00_00.UseRgss == 1)", "uniform-block instance read survives");
    check_contains(out, "highp vec2 param = _interface_variable_03;", "first statement of the if-body survives");
    check_contains(out, "} _uniform_instance_00_01;", "block instance name survives");
    check_contains(out, "uniform highp sampler2D _uniform_00_04;", "plain uniform declaration survives");
    check(out == mc263_preimage, "the whole shader is byte-identical afterwards");

    const std::string fog = process_uniform_declarations(mc263_fog_preimage);
    check(fog == mc263_fog_preimage, "the fog shader is byte-identical afterwards");
}

void test_initializer_stripping() {
    std::printf("\n-- uniform initialisers --\n");

    // The pass exists to drop initialisers: an initialised uniform is a constant to
    // glslang, and SPIRV-Cross gives it no name to bind against on the way back.
    check_contains(process_uniform_declarations("uniform vec4 Color = vec4(1.0);\n"), "uniform vec4 Color;\n",
                   "initialiser is stripped");
    check_lacks(process_uniform_declarations("uniform vec4 Color = vec4(1.0);\n"), "vec4(1.0)",
                "initialiser text is gone");

    // A precision the shader asked for itself has to survive the rewrite.
    check_contains(process_uniform_declarations("uniform lowp int N = 3;\n"), "uniform lowp int N;",
                   "the shader's own precision is kept");

    // Several declarations on one line: the pass ends at the first `;`.
    check_contains(process_uniform_declarations("uniform vec4 A = vec4(0.0), B = vec4(1.0);\n"),
                   "uniform vec4 A;", "multiple declarators");

    // Nothing to strip, nothing to change.
    check_contains(process_uniform_declarations("uniform vec4 Color;\n"), "uniform vec4 Color;\n",
                   "uninitialised uniform is untouched");
}

void test_keyword_positions() {
    std::printf("\n-- where the keyword may appear --\n");

    check_contains(process_uniform_declarations("uniform vec2 Texel = vec2(0.0);\n"), "uniform vec2 Texel;",
                   "keyword at offset 0");
    check_contains(process_uniform_declarations("float f = 1.0; uniform vec4 C = vec4(0.0);\n"),
                   "uniform vec4 C;", "keyword after a statement");
    check_contains(process_uniform_declarations("layout(std140) uniform Block\n{\n    mat4 M = mat4(1.0);\n} Inst;\n"),
                   "} Inst;", "block containing an initialiser passes through whole");
    check_contains(process_uniform_declarations("uniform vec4 u = vec4(1.0), outColor;\n"), "uniform vec4 u;",
                   "keyword after a comma");
}

void test_identifiers_containing_the_keyword() {
    std::printf("\n-- identifiers that merely contain the keyword --\n");
    // Individually, so a failure names the spelling that broke. Pristine turned
    // `myuniform = 1.0;` into `myuniform  ;` and `uniforms = 2.0;` into
    // `uniform s ;` -- the same corruption as 26.3, reached by an unrelated name.
    check(process_uniform_declarations("myuniform = 1.0;\n") == "myuniform = 1.0;\n", "myuniform");
    check(process_uniform_declarations("uniforms = 2.0;\n") == "uniforms = 2.0;\n", "uniforms");
    check(process_uniform_declarations("float uniforms = 2.0;\n") == "float uniforms = 2.0;\n",
          "uniforms as a declared name");
    check(process_uniform_declarations("vec4 gl_Uniform = vec4(0.0);\n") == "vec4 gl_Uniform = vec4(0.0);\n",
          "a name that only differs in case");
}

int count_of(const std::string& s, char c) {
    int n = 0;
    for (const char ch : s) {
        if (ch == c) ++n;
    }
    return n;
}

// The pass rewrites `uniform` declarations and is supposed to leave everything else
// byte-identical. These hold on any input, so they cover the shapes nobody thought to
// write a case for. Pristine deleted a block body and left an unbalanced brace behind,
// which no assertion in the suite above would have noticed.
void test_invariants_hold() {
    std::printf("\n-- invariants --\n");
    const char* inputs[] = {
        "uniform vec4 C = vec4(1.0);\nvoid main(){}\n",
        "layout(std140) uniform B\n{\n    mat4 M = mat4(1.0);\n} I;\nvoid main(){}\n",
        "void main(){ if (B.x == 1) { } }\n",
        "float myuniform = 1.0;\nvoid main(){ myuniform += 1.0; }\n",
        "uniform vec4 v = vec4(myuniform);\nvoid main(){}\n",
        "void main(){ { } }\n",
        "// a comment mentioning uniform\nvoid main(){}\n",
        "uniform vec4 C[4] = vec4[4](vec4(1.0),vec4(1.0),vec4(1.0),vec4(1.0));\nvoid main(){}\n",
    };
    for (const char* in : inputs) {
        // Labelled by its first line: a multi-line shader as a label wraps and buries
        // the assertion that failed.
        std::string label = in;
        const size_t nl = label.find('\n');
        if (nl != std::string::npos) label.erase(nl);

        const std::string once = process_uniform_declarations(in);
        const std::string twice = process_uniform_declarations(once.c_str());

        check(once == twice, "idempotent: " + label);
        check(count_of(once, '{') == count_of(once, '}'), "braces stay balanced: " + label);
    }
}

}  // namespace

int main() {
    std::printf("process_uniform_declarations regression tests\n");
    test_minecraft_263_is_untouched();
    test_initializer_stripping();
    test_keyword_positions();
    test_identifiers_containing_the_keyword();
    test_invariants_hold();

    std::printf("\n%s\n", failures ? "FAILURES" : "all tests passed");
    return failures ? 1 : 0;
}