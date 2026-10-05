import winsound, time, sys
time.sleep(1.5)
winsound.PlaySound(sys.argv[1], winsound.SND_FILENAME)
