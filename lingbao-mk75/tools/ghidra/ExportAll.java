// Ghidra headless post-script (tools/ghidra/run.sh): seeds the 8051 reset/interrupt vectors, re-runs analysis, writes decomp.c and listing.txt.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import java.io.*;
public class ExportAll extends GhidraScript {
  public void run() throws Exception {
    String out = getScriptArgs()[0];
    AddressSpace code = currentProgram.getAddressFactory().getDefaultAddressSpace();
    int[] vec = {0x00, 0x03, 0x0b, 0x13, 0x1b, 0x23, 0x2b, 0x33, 0x3b, 0x43, 0x4b, 0x53, 0x5b, 0x63, 0x6b, 0x73, 0x7b, 0x83, 0x8b};
    for (int v : vec) { Address a = code.getAddress(v); disassemble(a); if (getFunctionAt(a) == null) createFunction(a, String.format("vec_%02x", v)); }
    java.io.File seeds = new java.io.File(getSourceFile().getParentFile().getAbsolutePath(), "seeds.txt");
    if (seeds.exists()) for (String ln : java.nio.file.Files.readAllLines(seeds.toPath())) {
      ln = ln.trim(); if (ln.isEmpty() || ln.startsWith("#")) continue;
      Address a = code.getAddress(Long.parseLong(ln, 16)); disassemble(a); if (getFunctionAt(a) == null) createFunction(a, "seed_" + ln);
    }
    analyzeAll(currentProgram);
    DecompInterface di = new DecompInterface(); di.openProgram(currentProgram);
    try (PrintWriter c = new PrintWriter(out + "/decomp.c"); PrintWriter l = new PrintWriter(out + "/listing.txt")) {
      int n = 0;
      for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
        n++; DecompileResults r = di.decompileFunction(f, 60, monitor);
        c.println("// ==== " + f.getName() + " @ " + f.getEntryPoint());
        c.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// decompile failed: " + r.getErrorMessage());
      }
      for (Instruction i : currentProgram.getListing().getInstructions(true)) {
        Function f = getFunctionContaining(i.getAddress());
        l.println(i.getAddress() + "  " + i + (f != null && f.getEntryPoint().equals(i.getAddress()) ? "    ; <" + f.getName() + ">" : ""));
      }
      println("functions: " + n);
    }
  }
}
