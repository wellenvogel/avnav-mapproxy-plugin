boxes used for creating the seed information
primary source from https://github.com/free-x/mbtiles-nautical-boxes/tree/contrib/iho/contrib/iho

Many thanks to free-x!

After updating allcountries.bbox run

compute_missing.py allcountries.bbox computed.bbox 2

This will compute regions to have at most 2 empty layers between 2 tile
layers for each region.
They will not be shown at the map but will be considered for
computation.
