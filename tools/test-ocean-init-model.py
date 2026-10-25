"""Execute production init functions against a deterministic register model.
Only MMIO, counter, barriers and card responses are substituted. This cannot
validate Qualcomm silicon behavior, physical clocks or sector data reads.
"""
from pathlib import Path
import re, subprocess, tempfile, sys
source=Path(sys.argv[1]) if len(sys.argv)>1 else next(Path('dxb').rglob('bsd/dev/ocean_sdhci.c'))
s=source.read_text();s=s[s.index('static void delay_us'):s.index('static int map_host')]
s=re.sub(r'__asm__ volatile\(".*?"(?:\s*:::\s*"memory")?\);','/* host model barrier */',s)
assert '__asm__' not in s
prefix=r'''
#include <stdint.h>
#include <stdbool.h>
typedef uintptr_t vm_offset_t;
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
#include <stdlib.h>
static uint8_t host[4096];
static uint32_t core_mem[512], gcc_mem[0x80000/4];
static uintptr_t ocean_regs;
static int fault, phase, command_count, last_cmd, selected;
static unsigned commands[512];
static uint64_t counter;
static uint8_t r8(unsigned o) { return fault==7 && phase && o==0x29 ? 0 : host[o]; }
static uint16_t r16(unsigned o) { uint16_t v; memcpy(&v,host+o,2);return v; }
static uint32_t r32(unsigned o) { uint32_t v; memcpy(&v,host+o,4);return v; }
static void w32(unsigned o,uint32_t v) { memcpy(host+o,&v,4); }
static void w16(unsigned o,uint16_t v) {
 memcpy(host+o,&v,2);
 if(o==0x0e) {
  unsigned cmd=v>>8;assert(cmd==0||cmd==1||cmd==2||cmd==3||cmd==7);
  assert(command_count<512);commands[command_count++]=cmd;last_cmd=cmd;
  uint32_t response=cmd==1 ? (fault==5 ? 0x00ff8080U:0xc0ff8080U):0;
  if(cmd==3 && fault==6)response=0x80000000U;
  w32(0x10,response);
 }
}
static uintptr_t ml_io_map(uintptr_t pa,unsigned n) {
 if(pa==0x07824000 && n==0x800)return (uintptr_t)core_mem;
 if(pa==0x01800000 && n==0x80000)return (uintptr_t)gcc_mem;
 assert(0);return 0;
}
static int audit_io(uintptr_t va,uint64_t pa){(void)va;(void)pa;return 0;}
static uint64_t ticks(void) {
 counter+=19200;
 if(fault!=2 && host[0x2f]){host[0x2f]=0;phase=1;core_mem[0x78/4]=1;}
 uint32_t *cmd=&gcc_mem[0x42004/4];
 if((*cmd&2) && fault!=1)*cmd&=~0x80000001U;
 uint16_t clock=r16(0x2c);
 if(clock&1) {
  if(fault!=3 && !(fault==10 && (clock&4)))clock|=2;
  else clock&=~2U;
  memcpy(host+0x2c,&clock,2);
 }
 return counter;
}
static int wait_status(uint32_t mask) { assert(mask==1||mask==2);return fault==4 && last_cmd==0 ? ETIMEDOUT:0; }
static int command(unsigned cmd,uint32_t arg,uint8_t *data) {
 assert(cmd==13 && arg==65536 && !data);selected=1;return 0;
}
'''
suffix=r'''
static int run(int mode) {
 memset(host,0,sizeof host);memset(core_mem,0,sizeof core_mem);memset(gcc_mem,0,sizeof gcc_mem);
 fault=mode;phase=0;command_count=0;selected=0;counter=0;last_cmd=-1;
 ocean_regs=(uintptr_t)host;host[0x29]=11;core_mem[0xdc/4]=2;
 w32(0x10c,0x358b1c);gcc_mem[0x42008/4]=mode==8 ? 0x999:0x205;
 gcc_mem[0x42018/4]=mode==9 ? 0:1;gcc_mem[0x4201c/4]=1;
 gcc_mem[0x42004/4]=0x80000000U;
 if(mode==11){gcc_mem[0x42008/4]=0x2017;gcc_mem[0x42004/4]=2;gcc_mem[0x4200c/4]=1;gcc_mem[0x42010/4]=252;gcc_mem[0x42014/4]=251;}
 int error=initialize_card();
 if(mode==0 || mode==11) {
  unsigned expected[]={0,1,2,3,7};assert(!error && selected && command_count==5);
  assert(!memcmp(commands,expected,sizeof expected));
  assert((core_mem[0x78/4]&0x2001)==0x2001);
  assert(gcc_mem[0x42008/4]==0x2017);
  assert((r32(0x10c)&0x18000)==0x18000);
  assert((r16(0x2c)&7)==7 && !(r16(0x2c)&0xffc0));
 } else { assert(error && !selected); }
 if(mode==1||mode==2||mode==3||mode==7||mode==8||mode==9||mode==10)assert(!command_count);
 if(mode==4)assert(error==ETIMEDOUT && command_count==1);
 if(mode==5)assert(error==ENXIO && command_count>2);
 if(mode==6)assert(error==EIO && command_count==4);
 printf("MODEL CASE %d PASSED, result=%d commands=%d\n",mode,error,command_count);return 0;
}
int main(void){for(int i=0;i<=11;i++)run(i);puts("12 production-init model scenarios passed; hardware behavior unverified.");}
'''
with tempfile.TemporaryDirectory() as folder:
 p=Path(folder);(p/'model.c').write_text(prefix+s+suffix)
 subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror',str(p/'model.c'),'-o',str(p/'model')],check=True)
 subprocess.run([str(p/'model')],check=True)
