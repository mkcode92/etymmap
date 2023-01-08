# etymmap

Etymology from the Wiktionary in a Graph-App.

## What is etymmap?

Etymmap is a framework for extracting, analyzing and reducing etymology data from the English wiktionary.
Also, the resulting etymological graph can be interactively explored in a graph app.

The project consists of three parts:

1. etymmap library: extraction and common functionality
2. notebooks: statistical analyses of the historical dump and detailed analysis of a current dump
3. fronted: the app, based on [dash_cytoscape](https://dash.plotly.com/cytoscape) and backed
   by [neo4j](https://neo4j.com/)

## Getting started

You can either extract the most recent dump yourself or use the demo data, if you just want to try out the app.

### Setup

Project dependencies are managed with [poetry](https://python-poetry.org/docs/#installation).
Also, if you want to use a fully local setup, you may want to
use [docker-compose](https://docs.docker.com/compose/install/) for hosting mongodb (for extraction) and neo4j (for the
app).

Checkout the project and install the dependencies.

```
git clone https://github.com/mkcode92/etymmap.git
cd etymmap
poetry install --only main
```
In the last command, choose the dependency groups based on what you want to do:
* `main`: use etymmap to extract from a dump
* `main, notebooks`: execute the notebooks
* `main, app`: start the app from the script
* install everything with `poetry install`

If you only want to check out the app in docker with test data, you can also skip the poetry command.

### Extraction

To start with the extraction, you need a dump of the English wiktionary from [here](https://dumps.wikimedia.org/enwiktionary/), for example
https://dumps.wikimedia.org/enwiktionary/20230101/enwiktionary-20230101-pages-articles.xml.bz2.

The extraction follows the steps:
1. articles are parsed and stored in a mongodb
2. wiktionary can then be accessed through `etymmap.wiktionary.Wiktionary`
3. the graph is extracted

The last step requires a lot of ressources. If the entire lexicon is used, I recommend >= 12GB RAM.



### Exploration

## Details

The projects intends to make sense of etymological data as a graph.
This requires:

* a detailed ontology of etymological relations
* a lexeme-based model (i.e. one that distinguishes homonyms), otherwise some links and their transitive paths are just
  wrong (_manta ray_ is not derived from _ray_ "beam")
* non-redundancy:
    * through transitive reduction: A --> B --> C -> NOT (A --> C)
    * node unification

There are some challenges specific to the english wiktionary as the source of information:

* most etymological relations are expressed in particular markup entities, the **templates**.
  These can be used to extract a specific type and identify the participants of the relation.
  However, each template has to be parsed by it's own rules to extract a relation from it.
* not all articles use the templates, here a **rule-based** mechanism is used.
* redundancy: different sections encode overlapping graphs/trees.
    * many relations are specified at mulitple places
    * there are many _unspecific_ links between words that may be expressed _specific_ in other articles, here the most
      specific description has precedence
* linking: the target of a relation that is expressed by a template or wikilink has to be identifed, differentiating
  multiple meanings of a word, if necessary, by **comparing glosses**

----

Accompanying my master thesis "Erschließung etymologischer Daten des
Wiktionarys im Graphmodell" (_Aquisition of etymological data from the wiktionary through the graph model_) at
Universität Leipzig, Summer 2022.
