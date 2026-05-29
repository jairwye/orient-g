/** 从 Content-Disposition 解析下载文件名（支持 filename* UTF-8）。 */
export function parseContentDispositionFilename(
  header: string | null | undefined,
  fallback: string,
): string {
  if (!header) return fallback;
  const star = header.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].trim());
    } catch {
      // fall through
    }
  }
  const quoted = header.match(/filename\s*=\s*"([^"]+)"/i);
  if (quoted?.[1]) return quoted[1];
  const unquoted = header.match(/filename\s*=\s*([^;\s]+)/i);
  if (unquoted?.[1]) return unquoted[1];
  return fallback;
}
