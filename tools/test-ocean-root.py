"""Compile and exercise the production root-selection and HFS bounds helpers."""
from pathlib import Path
import subprocess
import tempfile
import sys
source = Path(sys.argv[1]) if len(sys.argv) > 1 else next(Path('dxb').rglob('bsd/dev/ocean_sdhci.c'))
s = source.read_text()
s = s[s.index('static bool root_candidate'):s.index('static int find_hfs')]
prefix = '#include <stdint.h>\n#include <stdbool.h>\n#include <string.h>\n#include <errno.h>\n#include <assert.h>\n#include <stdio.h>\n'
test = r'''
static void be(uint8_t *p, uint32_t n) { p[0]=n>>24;p[1]=n>>16;p[2]=n>>8;p[3]=n; }
int main(void) {
    uint64_t first=15826944, last=122142686, length=0;
    assert(!root_candidate("userdata",first,last,0));
    assert(!root_candidate("userdata",first,last,2));
    assert(!root_candidate("userdata",first+1,last,1));
    assert(!root_candidate("userdata",first,last-1,1));
    assert(!root_candidate("boot_a",first,last,1));
    assert(root_candidate("userdata",first,last,1));
    assert(root_candidate("IOS",first,last,0));
    uint8_t v[512]={0}; v[0]='H';v[1]='X';v[3]=5;
    be(v+40,4096);be(v+44,5242880);be(v+48,2897273);
    assert(!root_volume(v,last-first+1,true,&length));
    assert(length==41943040);
    assert(root_volume(v,length-1,true,&length)==EINVAL);
    v[0]='F';assert(root_volume(v,last-first+1,true,&length)==EINVAL);v[0]='H';
    v[3]=4;assert(root_volume(v,last-first+1,true,&length)==EINVAL);v[3]=5;
    be(v+40,513);assert(root_volume(v,last-first+1,true,&length)==EINVAL);
    be(v+40,4096);be(v+44,0);assert(root_volume(v,last-first+1,true,&length)==EINVAL);
    be(v+44,5242881);assert(root_volume(v,last-first+1,true,&length)==EINVAL);
    be(v+44,5242880);be(v+48,5242881);assert(root_volume(v,last-first+1,true,&length)==EINVAL);
    be(v+48,0);be(v+40,65536);be(v+44,0xffffffff);
    assert(root_volume(v,last-first+1,false,&length)==EINVAL);
    puts("15 production root-selector and HFS bounds checks passed");
}
'''
with tempfile.TemporaryDirectory() as folder:
    p=Path(folder)
    (p/'test.c').write_text(prefix+s+test)
    subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
