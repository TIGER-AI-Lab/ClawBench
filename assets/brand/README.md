# ClawBench logo

The mark combines a paw, a mouse-pointer cutout, and a bench. The coral mark works on light and dark backgrounds; the wordmark has separate light and dark versions.

| Asset | Use |
| --- | --- |
| [clawbench-logo.svg](../clawbench-logo.svg) | Horizontal logo on light backgrounds |
| [clawbench-logo-dark.svg](../clawbench-logo-dark.svg) | Horizontal logo on dark backgrounds |
| [clawbench-mark.svg](../clawbench-mark.svg) | Standalone icon or avatar |

All assets are transparent SVGs. Lettering is stored as paths, so rendering does not depend on installed fonts. Use the standalone mark for small placements and leave space around it.

Colors: coral `#EB6449`, ink `#20242C`, ivory `#F3F1ED`. The README uses a darker coral `#B84A34` behind white badge lettering.

The wordmark uses outlined [Manrope](https://github.com/googlefonts/manrope), weight 720, with optical spacing and kerning. Its [SIL Open Font License](Manrope-OFL.txt) is included here.

The README heading icons share the coral accent. Workflow illustrations have English and Chinese text, wide and narrow layouts, and light and dark variants. The narrow version uses larger lettering and a fixed intrinsic width so GitHub's sidebar does not shrink the four-column diagram into unreadable text.

Edit [generate_workflow.py](generate_workflow.py) to change labels, colors, or geometry. Regenerate all eight variants with no extra dependencies:

```bash
python3 assets/brand/generate_workflow.py
python3 assets/brand/generate_workflow.py --check
```
