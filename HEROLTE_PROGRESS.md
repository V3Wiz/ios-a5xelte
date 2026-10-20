# HEROLTE (Galaxy S7 SM-G930F, Exynos 8890): progreso

Registrar por separado: compilación, marcadores recuperados, lo que se ve en
pantalla y comportamiento de iOS. Plan y mapa de hardware en
`docs/herolte-bringup.md`.

## 2026-10-20

- Dispositivo: SM-G930F, bootloader desbloqueado, TWRP instalado.
- `shim/herolte/probe.S` + `probe.c` compilados con Arm GNU Toolchain 14.2.rel1
  (`aarch64-none-elf`): Image de 10.784 bytes, solo relocaciones PC-relativas
  (ADR_PREL_PG_HI21, ADD_ABS_LO12_NC, CALL26), sin llamadas a librería.
  **Solo compilación**; no se ejecutó en el teléfono.
- `tools/herolte-pack-boot.py` probado con una imagen BOOT sintética
  (página de 2048, DTBH v2 con chip 8890): conserva DTBH y ramdisk, copia
  `text_offset`/flags del kernel de stock, recalcula el SHA-1 del header.
  Todavía no se probó con el BOOT real del S7.
- BOOT del teléfono (custom ROM, no stock), leído con `dd` desde TWRP:
  partición de 41.943.040 bytes, página 2048, kernel arm64 sin comprimir de
  38 MB con `text_offset=0x80000`, DTBH v2 con 3 DTB Exynos 8890
  (hw_rev 4–7, 8, 9). DTB: RAM `0x80000000+0x7e400000` y `0x880000000+2G`,
  initrd en `0x82000000`, reservas TIMA `0xb1000000`, ION desde
  `0xc0000000`, módem `0xf0000000`. `0xe2a00000` cae en un hueco libre.
- `probe-boot.img` armado desde ese BOOT (1.495.056 bytes).
- **Primera prueba en el teléfono (reporte del usuario):** el probe muestra
  texto blanco sobre el logo y la cuenta "TWRP EN 60 S"; al terminar, el
  teléfono reinicia solo a TWRP. Prueba que S-Boot ejecuta nuestro Image
  (header arm64 + DTBH correctos), que el framebuffer `0xe2a00000` con el HW
  trigger de DECON_F funciona, que CNTPCT avanza y que el reinicio a
  recovery por PMU `0x105c0000` (INFORM2/INFORM3/SWRESET) funciona.
- **Foto del probe:** EL 1; SCTLR `0x30c5183e` (MMU off); FDT `0x8a000000`;
  IMAGE `0x800bc000`; MIDR `0x410fd034` (Cortex-A53 r0p4); MPIDR
  `0x80000100`; MMFR0 `0x1122` (sin 16 KiB); PFR0 `0x2222`; ISAR0 `0x11120`
  (AES/SHA1/SHA2/CRC32, **sin LSE**); CNTFRQ **0** (como el A5: frecuencia
  desde el ADT, 26 MHz); DECON trigger previo `0x12b0`; initrd
  `0x89000000..0x890dbf7e` (el ramdisk de la ROM).
- Consecuencia: entre initrd y FDT hay 16 MiB, poco para el payload de XNU.
  `xnu_boot` ahora busca el payload pegado a su Image
  (`herolte-pack-boot.py --append`) y usa el initrd solo como alternativa.
- Serie de parches normalizada sobre `xnu-8796.141.3` (ver
  `docs/herolte-bringup.md`): 123 parches aplican con `git apply` simple,
  incluido `0200-herolte-board-target`. 12 movidos a `xnu/patches-pending/`
  (los 10 rotos m?s `0133`/`0134` de GPU del A5, publicados despu?s).
  **El kernel HEROLTE todavía no se compiló**: Actions pendiente.
- `shim/herolte/xnu_boot` (loader) y `tools/mkadt_herolte.py` escritos y
  compilados/ejecutados localmente; sin prueba en el teléfono.
- `0106`/`0107` reescritos como `0201-herolte-amfi-bridge` y
  `0202-herolte-4k-unsigned-dyld-cache`; 125 parches aplican en orden.
- **Primer kernel HEROLTE compilado en Actions** (fork `wardevsa/ios-a5xelte`,
  rama `herolte`, run 39477885586, commit fb6194b): artefacto `xnu-kernel`
  de 61 MB. El chequeo de LSE encontró una sola coincidencia, dentro de
  `K256` (constantes de SHA-256 en `__TEXT`), es decir, datos: el código del
  kernel no tiene atómicas LSE. El chequeo ahora ignora `K256`.
- Actions publica los errores de compilación como anotaciones públicas
  (los logs requieren sesión de GitHub).
- **Primer arranque de XNU en el S7** (`xnu-boot.img`: loader + payload
  pegado de 16.474.720 bytes; kernel sha256 `61a9dd49…ca5d`, cmdline
  `debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress`).
  Foto del usuario: consola de XNU en el framebuffer con VM bootstrap,
  zone_init, firehose, scheduler, KDP serial, `iBoot version: herolte-entry`,
  `SWEET PRNG`, `A5XELTE pthread: libpthread-514.100.2 registered`,
  `SWEET AMFI: built-in interface registered`, platform expert iniciado.
  Pánico en `SweetCPU.cpp:86`: `unsupported topology cpu=0 mpidr=0x100
  count=1` (el chequeo esperaba MPIDR 0 del A5).
- `0203-herolte-boot-mpidr`: el MPIDR de arranque es constante de placa
  (`A5XELTE_BOOT_MPIDR`: A5 `0x0`, herolte `0x100`).
- **Kernel completo hasta la espera del root** (run 39481021599, kernel
  sha256 `ffa3d8ea…432f`, misma cmdline). Foto del usuario: `A5XELTE CPU:
  cpu=0 mpidr=0x100 came alive; SGI1 OK`, `1/1 CPUs initialized, SGI1
  verified`, BSD init, AppleKeyStore, IOWatchdog, IOCoreSurfaceRoot, HID de
  botones/touch, SWEET AMFI (0201) y Sandbox registrados, HFS 627.100.6,
  self-tests de Skywalk `PASSED`, `lo0`/`gif0`/`stf0`, y finalmente
  `Waiting on <dict>IOProviderClass IOMedia, Content Apple_HFS</dict>`.
  Es el punto esperado: no hay driver de almacenamiento todavía.
- **Primer probe UFS** (`0204`, run 39484347438, kernel `d3905386…45f2`,
  `ufsprobe=1`): `cap 0x383ff0f ver 0x200 hcs 0x10f hce 0x1 is 0
  utrlba 0x0:ef002000 dbr 0 rsr 1`, `txprdt 0xc rxprdt 0xc nexus 0xffff`.
  El host quedó vivo tras S-Boot y tomó nuestra lista. TEST UNIT READY en
  LUN 0 (3 veces): `ocs 0x7 upiu 0x21 response 0x1 status 0x2`, o sea un
  UPIU de respuesta real con CHECK CONDITION: el transporte (UTRD con
  offsets en bytes, PRDT, NEXUS, doorbell) funciona. El probe no siguió a
  READ porque abortaba tras el TUR. Siguiente: imprimir el sense, probar
  LUN 0..7 y leer LBA1 aunque falle el TUR.
- **Segundo probe UFS** (run 39486812960, kernel `00f0b0da…deb1`): LUN 0–3
  responden NOT READY (sense key 2, ASC/ASCQ 0/0); LUN 4–7 ILLEGAL REQUEST
  ASC 0x25 (no existen: el S7 tiene 4 LU). READ(10) LBA1 en LUN 0: NOT
  READY. Hipótesis: S-Boot deja el dispositivo en un modo de bajo consumo;
  Linux lo reactiva con START STOP UNIT (ACTIVE) al W-LUN UFS Device
  (`0xD0`). `0204` ahora lo hace antes del primer comando (probe e init).
- **Tercer probe UFS: lectura funcionando** (run 39489906319, kernel
  `869c4c5f…d74a`). W-LUN `0xD0` TUR: NOT READY ASC/ASCQ 04/02
  ("initializing command required"); `START STOP UNIT (ACTIVE) 0`; LUN 0–3
  TEST UNIT READY 0; `READ(10) LBA1 0, signature EFI PART`; GPT de 128
  entradas de 128 bytes en LBA 2; particiones p1 `BOTA0` … p17 `USERDATA`
  (~21,5 GB, bloques de 4 KiB). Primera lectura del UFS desde XNU.
- Pendiente: nodo `/product` del ADT a partir del IPSW; root (UFS).
