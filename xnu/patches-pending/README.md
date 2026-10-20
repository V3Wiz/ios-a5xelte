# Parches pendientes

No aplican sobre la serie normalizada de `xnu/patches/`: se generaron contra
estados de archivo que la serie publicada del A5 no reproduce. Hay que
reescribirlos a mano antes de moverlos de vuelta.

| Parche | Para HEROLTE |
| --- | --- |
| 0106 amfi-bridge | **Necesario** para ejecutar launchd (interfaz AMFI integrada) |
| 0107 4k-unsigned-dyld-cache | **Necesario** para cargar la shared cache de 16 KiB con páginas de 4 KiB |
| 0112, 0113, 0115 SMP | Más adelante (arrancar con `cpus=1`) |
| 0116 container-entitlement-trace | Diagnóstico, opcional |
| 0129–0134 G3D | Específicos de la Mali-T720 del A5; no aplican al S7 |
