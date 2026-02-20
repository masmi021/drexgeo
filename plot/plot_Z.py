#!/usr/bin/env python
# encoding: utf-8

import os, sys
import matplotlib.pyplot as plt
import numpy as np
import json


infile = sys.argv[1]

with open(infile, 'r') as json_file:  
  data = json.load(json_file)


  T  =1/np.array(data['Data']['Freq']) 
  Zxx = np.array(data['Data']['Z']['xx']['Re']) + 1j*np.array(data['Data']['Z']['xx']['Im'])
  Zxy = np.array(data['Data']['Z']['xy']['Re']) + 1j*np.array(data['Data']['Z']['xy']['Im'])
  Zyx = np.array(data['Data']['Z']['yx']['Re']) + 1j*np.array(data['Data']['Z']['yx']['Im'])
  Zyy = np.array(data['Data']['Z']['yy']['Re']) + 1j*np.array(data['Data']['Z']['yy']['Im'])
  errZxx = np.sqrt(data['Data']['Z']['xx']['Var'])
  errZxy = np.sqrt(data['Data']['Z']['xy']['Var']) 
  errZyx = np.sqrt(data['Data']['Z']['yx']['Var']) 
  errZyy = np.sqrt(data['Data']['Z']['yy']['Var']) 

  RelErrZxy = errZxy/np.abs(Zxy) 
  RelErrZyx = errZxy/np.abs(Zxy)



  #create 2 subplots rho, phase  
  plt.rcParams["font.family"] = "sans-serif"
  plt.rcParams["font.size"] = 16
  plt.rcParams["font.sans-serif"] = ["Times"]

  fig, ax = plt.subplots(nrows=2, ncols=1, figsize=(8, 8))
  
  #rho
  ax[0].errorbar(np.log10(T), np.log10(0.2*T*np.abs(Zxy**2)), yerr=RelErrZxy*2,
               fmt='bo', markersize=7,fillstyle='none')
  ax[0].errorbar(np.log10(T), np.log10(0.2*T*np.abs(Zyx**2)), yerr=RelErrZyx*2,
               fmt='rv', markersize=7,fillstyle='none')
  ax[0].grid(True,color='0.9')
  ax[0].set(ylabel='lg($ρ_a$[Ωm])',
       title=data['Header']['Site']['Name'])
  
  #phase
  ax[1].errorbar(np.log10(T), np.angle(Zxy, deg=True), yerr=RelErrZxy*180/np.pi,
               fmt='bo', markersize=7,fillstyle='none')
  ax[1].errorbar(np.log10(T), np.angle(-Zyx, deg=True), yerr=RelErrZyx*180/np.pi,
               fmt='rv', markersize=7,fillstyle='none')
  ax[1].grid(True,color='0.9')
  ax[1].set(xlabel='lg(T[s])', ylabel='$φ_Z$[deg]')
  
  plt.show()
  fig.savefig(infile+".pdf")
  




