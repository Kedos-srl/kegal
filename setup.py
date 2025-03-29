from setuptools import setup

setup(
   name='kegal',
   version='0.1',
   description='KeGAL is a graph-based agent framework for LLMs',
   author='Fabio Gagliardi',
   author_email='fabio.gagliardi@kedos-srl.it',
   packages=['kegal'],  #same as name
   install_requires=['networkx', 'yaml', 'ollama', 'openai'], #external packages as dependencies
)