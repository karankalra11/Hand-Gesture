import sys
import os
import cv2
import numpy as np
from scipy.cluster.vq import kmeans, vq
from sklearn import svm
from feature_extractor import FeatureExtractor
from hand_tracker import HandTracker
from sklearn import model_selection
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import jaccard_similarity_score

class Trainer(object):
    def __init__(self, numGestures, numFramesPerGesture, minDescriptorsPerFrame, numWords, descType, kernel, numIter, parent):
        self.numGestures = numGestures
        self.numFramesPerGesture = numFramesPerGesture
        self.numWords = numWords
        self.minDescriptorsPerFrame = minDescriptorsPerFrame
        self.parent = parent
        self.desList = []
        self.voc = None
        self.classifier = None
        self.windowName = "Training preview"
        self.handWindowName = "Cropped hand"
        self.binaryWindowName = "Binary frames"
        self.handTracker = HandTracker(kernelSize=7, thresholdAngle=0.4, defectDistFromHull=30, parent=self)
        self.featureExtractor = FeatureExtractor(type=descType, parent=self)
        self.kernel = kernel
        self.numIter = numIter
        self.numDefects = None
        self.firstFrameList = []
        self.trainLabels = []

    def extract_descriptors_from_images(self, gestureDirList, parentDirPath, trainMask, maskParentDirPath):
        #self.numFramesPerGestureList = []
        for i,gestureDir in enumerate(gestureDirList):
            gestureDirPath = os.path.join(parentDirPath, gestureDir)
            imgList = []
            for dirpath, dirnames, filenames in os.walk("%s" % (gestureDirPath), topdown=True, followlinks=True):
                for f in filenames:
                    if f.endswith(".jpg"):
                        imgList.append(os.path.join(dirpath, f))
            if trainMask != 0:
                maskList = []
                maskDirPath = os.path.join(maskParentDirPath, gestureDir)
                for dirpath, dirnames, filenames in os.walk("%s" % (maskDirPath), topdown=True, followlinks=True):
                    for f in filenames:
                        if f.endswith(".bmp"):
                            maskList.append(os.path.join(dirpath, f))

            #self.numFramesPerGestureList.append(len(imgList))
            gestureID = i+1
            for j,f in enumerate(imgList):
                cropImage = cv2.imread(f)
                cropImage = cv2.flip(cropImage, 1)
                cropImageGray = cv2.cvtColor(cropImage, cv2.COLOR_BGR2GRAY)
                kp = self.featureExtractor.get_keypoints(cropImageGray)
                if trainMask != 0:
                    mask = cv2.imread(maskList[j])
                    mask = cv2.flip(mask, 1)
                    mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
                    if trainMask > 0:
                        ret,binaryIm = cv2.threshold(mask,127,255,cv2.THRESH_BINARY)
                    else:
                        ret,binaryIm = cv2.threshold(mask,127,255,cv2.THRESH_BINARY_INV)
                    binaryIm = cv2.dilate(binaryIm, self.handTracker.kernel, iterations = 1)
                    cnt,hull,centroid,defects = self.handTracker.get_contour(binaryIm, False)
                    kp = self.featureExtractor.get_keypoints_in_contour(kp, cnt)
                else:
                    kp = self.featureExtractor.get_keypoints(cropImageGray)
                kp,des = self.featureExtractor.compute_descriptors(cropImageGray, kp)
                #kp,des = self.featureExtractor.get_keypoints_and_descriptors(cropImageGray)
                if des is not None and des.shape[0] >= 0:
                    self.featureExtractor.draw_keypoints(cropImage, kp)
                    self.desList.append(des)
                    self.trainLabels.append(gestureID)
                if j == 0:
                    self.firstFrameList.append(cropImage)
                cv2.imshow(self.handWindowName, cropImage)
                k = cv2.waitKey(1)
                if k == 27:
                    sys.exit(0)
        cv2.destroyAllWindows()

    def extract_descriptors_from_video(self):
        vc = self.parent.vc
        while(vc.isOpened()):
            ret,im = vc.read()
            im = cv2.flip(im, 1)
            imhsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
            self.handTracker.colorProfiler.draw_color_windows(im, imhsv)
            cv2.imshow(self.windowName, im)
            k = cv2.waitKey(1)
            if k == 32: # space
                break
            elif k == 27:
                sys.exit(0)

        self.handTracker.colorProfiler.run()
        binaryIm = self.handTracker.get_binary_image(imhsv)
        cnt,hull,centroid,defects = self.handTracker.initialize_contour(binaryIm)
        self.numDefects = np.zeros((self.numGestures,self.numFramesPerGesture), "uint8")
        cv2.namedWindow(self.binaryWindowName)
        cv2.namedWindow(self.handWindowName)
        cv2.namedWindow(self.windowName)

        #self.numFramesPerGestureList = [self.numFramesPerGesture] * self.numGestures
        gestureID = 1
        frameNum = 0
        captureFlag = False
        while(vc.isOpened()):
            ret,im = vc.read()
            im = cv2.flip(im, 1)
            imhsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
            imgray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
            binaryIm = self.handTracker.get_binary_image(imhsv)
            cnt,hull,centroid,defects = self.handTracker.get_contour(binaryIm)
            imCopy = 1*im
            if cnt is not None:
                cropImage,cropPoints = self.handTracker.get_cropped_image_from_cnt(im, cnt, 0.05)
                cropImageGray = self.handTracker.get_cropped_image_from_points(imgray, cropPoints)
                #cv2.fillPoly(binaryIm, cnt, 255)
                #cropImageBinary = self.handTracker.get_cropped_image_from_points(binaryIm, cropPoints)
                #cropImageGray = self.apply_binary_mask(cropImageGray, cropImageBinary, 5)
                #kp,des = self.featureExtractor.get_keypoints_and_descriptors(cropImageGray)
                kp = self.featureExtractor.get_keypoints(cropImageGray)
                cropCnt = self.handTracker.get_cropped_contour(cnt, cropPoints)
                kp = self.featureExtractor.get_keypoints_in_contour(kp, cropCnt)
                kp,des = self.featureExtractor.compute_descriptors(cropImageGray, kp)
                if des is not None and des.shape[0] >= 0:
                    self.featureExtractor.draw_keypoints(cropImage, kp)
                #x = int(cropPoints[0])
                #y = int(cropPoints[1])
                #w = int(cropPoints[2])
                #h = int(cropPoints[3])
                #cv2.rectangle(imCopy,(x,y),(x+w,y+h),(0,255,0),2)
                if captureFlag:
                    if frameNum == 0:
                        self.firstFrameList.append(im)
                    if des is not None and des.shape[0] >= self.minDescriptorsPerFrame and self.is_hand(defects):
                        self.desList.append(des)
                        self.trainLabels.append(gestureID)
                        self.handTracker.draw_on_image(imCopy, cnt=False, hullColor=(0,255,0))
                        self.numDefects[gestureID-1][frameNum] = defects.shape[0]
                        frameNum += 1
                    else:
                        self.handTracker.draw_on_image(imCopy, cnt=False, hullColor=(0,0,255))
                    if frameNum >= self.numFramesPerGesture:
                        if gestureID >= self.numGestures:
                            break
                        else:
                            captureFlag = False
                            gestureID += 1
                            frameNum = 0
                else:
                    self.handTracker.draw_on_image(imCopy, cnt=False)
                cv2.imshow(self.handWindowName, cropImage)
            if not captureFlag:
                text = "Press <space> for new gesture {0}".format(gestureID)
            else:
                text = "Getting gesture {0}".format(gestureID)
            self.write_on_image(imCopy, text)
            cv2.imshow(self.binaryWindowName, binaryIm)
            cv2.imshow(self.windowName,imCopy)
            k = cv2.waitKey(1)
            if not captureFlag:
                #print "Press <space> for new gesture <{0}>!".format(gestureID)
                if k == 32:
                    captureFlag = True
                    continue
            if k == 27:
                sys.exit(0)
            elif k == 99:
                cv2.imwrite("TrainingImage.jpg", imCopy)
                cv2.imwrite("BinaryImage.jpg", binaryIm)
                cv2.imwrite("CroppedImage.jpg", cropImage)
        cv2.destroyAllWindows()

    def apply_binary_mask(self, image, mask, kernelSize):
        kernel = np.ones((kernelSize,kernelSize),np.uint8)
        dilatedMask = cv2.dilate(mask,kernel,iterations=1)
        maskedImage = cv2.bitwise_and(image, image, mask=dilatedMask)
        return maskedImage

    def kmeans(self):
        print "Running k-means clustering with {0} iterations...".format(self.numIter)
        descriptors = self.desList[0]
        for des in self.desList:
            descriptors = np.vstack((descriptors, des))
        if descriptors.dtype != "float32":
            descriptors = np.float32(descriptors)
        self.voc,variance = kmeans(descriptors, self.numWords, self.numIter)
        return variance

    def bow(self):
        print "Extracting bag-of-words features for {0} visual words...".format(self.numWords)
        self.trainData = np.zeros((len(self.trainLabels), self.numWords), "float32")
        for i in range(len(self.trainLabels)):
            words, distance = vq(self.desList[i], self.voc)
            for w in words:
                self.trainData[i][w] += 1
        normTrainData = np.linalg.norm(self.trainData, ord=2, axis=1) * np.ones((self.numWords,1))
        self.trainData = np.divide(self.trainData, normTrainData.T)

    def svm(self):
        print "Training SVM classifier with {0} kernel...".format(self.kernel)
        if self.kernel == "linear":
            clf = svm.LinearSVC()
            valScore = self.leave_one_out_validate(clf)
            print "Training score video linear= {0}".format(valScore)
            '''
        #elif self.kernel == "hist":
            from sklearn.metrics.pairwise import additive_chi2_kernel
            #clf13 = svm.SVC(kernel=additive_chi2_kernel, decision_function_shape='ovr')
            #valScore = self.leave_one_out_validate(clf13)
            #print "Training score video hist= {0}".format(valScore)
        #elif self.kernel == "tree": #decition tree
            from sklearn import tree
            clf12 = tree.DecisionTreeClassifier()
            valScore = self.leave_one_out_validate(clf12)
            print "Training score video tree= {0}".format(valScore)
        #elif self.kernel == "nural": #neural network backpropogation
            from sklearn.neural_network import MLPClassifier
            clf11 = MLPClassifier(solver='lbfgs', alpha=1e-5, hidden_layer_sizes=(5, 2), random_state=1)
            MLPClassifier(activation='relu', alpha=1e-05, batch_size='auto', beta_1=0.9, beta_2=0.999, early_stopping=False, epsilon=1e-08, hidden_layer_sizes=(5, 2), learning_rate='constant', learning_rate_init=0.001, max_iter=200, momentum=0.9, nesterovs_momentum=True, power_t=0.5, random_state=1, shuffle=True, solver='lbfgs', tol=0.0001, validation_fraction=0.1, verbose=False, warm_start=False)
            #from sknn.mlp import Classifier, Layer
            #clf11 = Classifier(layers=[Layer("Maxout", units=100, pieces=2), Layer("Softmax")], learning_rate=0.001, n_iter=25)
            valScore = self.leave_one_out_validate(clf11)
            print "Training score video nural= {0}".format(valScore)
        #elif self.kernel == "sgd": #stochastic gradient decendent
            from sklearn.linear_model import SGDClassifier
            clf10 = SGDClassifier(loss="log", penalty="l2")
            SGDClassifier(alpha=0.0001, average=False, class_weight=None, epsilon=0.1, eta0=0.0, fit_intercept=True, l1_ratio=0.15, learning_rate='optimal', loss='log', n_iter=5, n_jobs=1, penalty='l2', power_t=0.5, random_state=None, shuffle=True, verbose=0, warm_start=False)
            valScore = self.leave_one_out_validate(clf10)
            print "Training score video sgd= {0}".format(valScore)
        #elif self.kernel == "forest":
            from sklearn.ensemble import RandomForestClassifier
            clf9 = RandomForestClassifier(n_estimators=10)
            valScore = self.leave_one_out_validate(clf9)
            print "Training score video forest= {0}".format(valScore)
        #elif self.kernel == "bagging":
            #from sklearn.ensemble import BaggingClassifier
            #from sklearn.neighbors import KNeighborsClassifier
            #clf8 = BaggingClassifier(KNeighborsClassifier(), max_samples=0.5, max_features=0.5)
            #valScore = self.leave_one_out_validate(clf8)
            #print "Training score video bagging= {0}".format(valScore)
        #elif self.kernel == "gradientBoost":
            from sklearn.ensemble import GradientBoostingClassifier
            #clf7 = GradientBoostingClassifier(n_estimators=100, learning_rate=1.0, max_depth=1, random_state=0)
            #valScore = self.leave_one_out_validate(clf7)
            #print "Training score video gradientBoost= {0}".format(valScore)
        #elif self.kernel == "voting":
            from sklearn.ensemble import VotingClassifier
            from itertools import product
            #clf1 = svm.LinearSVC()
            #from sklearn import tree
            #clf2 = tree.DecisionTreeClassifier()
            #from sknn.mlp import Classifier, Layer
            #clf3 = Classifier(layers=[Layer("Maxout", units=100, pieces=2), Layer("Softmax")], learning_rate=0.001, n_iter=25)
            #from sklearn.linear_model import SGDClassifier
            #clf4 = SGDClassifier(loss="log", penalty="l2")
            #SGDClassifier(alpha=0.0001, average=False, class_weight=None, epsilon=0.1, eta0=0.0, fit_intercept=True, l1_ratio=0.15, learning_rate='optimal', loss='log', n_iter=5, n_jobs=1, penalty='l2', power_t=0.5, random_state=None, shuffle=True, verbose=0, warm_start=False)
            #from sklearn.ensemble import RandomForestClassifier
            #clf5 = RandomForestClassifier(n_estimators=10)
            clf = VotingClassifier(estimators=[('linear', clf14), ('tree', clf12), ('nural', clf11), ('sgd', clf10), ('forest', clf9)], voting='hard')
            valScore = self.leave_one_out_validate(clf)
            print "Training score video voting= {0}".format(valScore)
            '''
        else:
            clf = svm.SVC(kernel=self.kernel, decision_function_shape='ovr', degree=2, gamma=2)
            valScore = self.leave_one_out_validate(clf6)
            print "Training score video SVC= {0}".format(valScore)
        valScore = self.leave_one_out_validate(clf)
        clf.fit(self.trainData, self.trainLabels)
        #MLPClassifier(activation='relu', alpha=1e-05, batch_size='auto', beta_1=0.9, beta_2=0.999, early_stopping=False, epsilon=1e-08, hidden_layer_sizes=(5, 2), learning_rate='constant', learning_rate_init=0.001, max_iter=200, momentum=0.9, nesterovs_momentum=True, power_t=0.5, random_state=1, shuffle=True, solver='lbfgs', tol=0.0001, validation_fraction=0.1, verbose=False, warm_start=False)
        #SGDClassifier(alpha=0.0001, average=False, class_weight=None, epsilon=0.1, eta0=0.0, fit_intercept=True, l1_ratio=0.15, learning_rate='optimal', loss='hinge', n_iter=5, n_jobs=1, penalty='l2', power_t=0.5, random_state=None, shuffle=True, verbose=0, warm_start=False)
        self.classifier = clf
        self.classifier.voc = self.voc
#        if self.numDefects is not None:
#            self.classifier.medianDefects = np.median(self.numDefects, axis=1)
#        else:
#            self.classifier.medianDefects = None
        return valScore

    def leave_one_out_validate(self, clf):
        fullTrainData = self.trainData
        fullTrainLabels = self.trainLabels
        accuracy = np.zeros(len(fullTrainLabels))
        for i in range(len(fullTrainLabels)):
            testData = fullTrainData[i]
            testLabels = fullTrainLabels[i]
            trainData = np.append(fullTrainData[:i], fullTrainData[i+1:], axis=0)
            trainLabels = np.append(fullTrainLabels[:i], fullTrainLabels[i+1:])
            #clf = svm.LinearSVC()
            clf.fit(trainData, trainLabels)
            prediction = clf.predict(testData.reshape(1,-1))
            #score = clf.decision_function(testData.reshape(1,-1))
            if prediction != testLabels:
                accuracy[i] = 0
            else:
                accuracy[i] = 1
        #jac=jaccard_similarity_score(testLabels, prediction)
        return np.mean(accuracy)
        #return jac
        
        
    def predict(self, testData):
        prediction = self.classifier.predict(testData.reshape(1,-1))
        score = self.classifier.decision_function(testData.reshape(1,-1))
        return prediction[0], score[0]

    def is_hand(self, defects):
        if defects.shape[0] > 4:
            return False
        else:
            return True

    def write_on_image(self, image, text):
        cv2.putText(image, text, (self.parent.imWidth/20,self.parent.imHeight/10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
