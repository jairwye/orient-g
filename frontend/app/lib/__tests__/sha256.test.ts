import { sha256HexFromBytes, sha256HexFromFileForUpload, sha256HexPure } from "../sha256";

describe("sha256", () => {
  it("pure implementation matches known empty hash", () => {
    expect(sha256HexPure(new Uint8Array([]))).toBe(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
  });

  it("sha256HexFromBytes works without subtle (forced pure path)", async () => {
    const subtle = globalThis.crypto?.subtle;
    Object.defineProperty(globalThis.crypto, "subtle", { value: undefined, configurable: true });
    try {
      const text = Uint8Array.from([104, 101, 108, 108, 111]); // "hello"
      const hex = await sha256HexFromBytes(text);
      expect(hex).toBe("2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824");
    } finally {
      Object.defineProperty(globalThis.crypto, "subtle", { value: subtle, configurable: true });
    }
  });

  it("upload helper never needs subtle", async () => {
    const subtle = globalThis.crypto?.subtle;
    Object.defineProperty(globalThis.crypto, "subtle", { value: undefined, configurable: true });
    try {
      const file = { arrayBuffer: async () => Uint8Array.from([97]).buffer } as unknown as File;
      const hex = await sha256HexFromFileForUpload(file);
      expect(hex).toHaveLength(64);
    } finally {
      Object.defineProperty(globalThis.crypto, "subtle", { value: subtle, configurable: true });
    }
  });
});
