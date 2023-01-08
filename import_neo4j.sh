DIR=$1
# import everything into a fresh database
docker run --interactive --tty --rm \
           --publish=7474:7474 --publish=7687:7687 \
           --volume=$PWD/.neo4j/data:/data \
           --volume=$PWD/.neo4j/import:/import \
           --user root \
           neo4j:4.4.6 neo4j-admin import \
           --force \
           --skip-bad-entries-logging=true \
           --bad-tolerance=2000 \
           --nodes=Word:EtymologyEntry=/import/$DIR/etymology_entry.csv \
           --nodes=Word:Entity=/import/$DIR/entity.csv \
           --nodes=Word:NAE=/import/$DIR/nae.csv \
           --nodes=Attr:POS=/import/$DIR/pos.csv \
           --nodes=Attr:Gloss=/import/$DIR/gloss.csv \
           --nodes=Attr:Pronunc=/import/$DIR/pronunciation.csv \
           --relationships=/import/$DIR/etymology.csv \
           --relationships=HAS_POS=/import/$DIR/has_pos.csv \
           --relationships=HAS_GLOSS=/import/$DIR/has_gloss.csv \
           --relationships=HAS_PRONUNC=/import/$DIR/has_pronunciation.csv \
           --multiline-fields=true \
           --delimiter="," \
           --array-delimiter="@" \
           --database=etymmap
