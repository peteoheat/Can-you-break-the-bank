import unittest

try:
    import numpy as np
    from face_engine import SimulatedFaceEngine, simulated_landmarks
except ImportError:  # the other tests don't need numpy, so a bare Python can still run them
    raise unittest.SkipTest("numpy is not installed")

FEATURES = {"chin", "left_eyebrow", "right_eyebrow", "nose_bridge", "nose_tip",
            "left_eye", "right_eye", "top_lip", "bottom_lip"}


class SimulatedLandmarksTests(unittest.TestCase):
    box = (50, 350, 250, 150)  # top, right, bottom, left

    def test_has_the_features_face_recognition_names(self):
        self.assertEqual(set(simulated_landmarks(self.box)), FEATURES)

    def test_points_are_inside_the_box(self):
        top, right, bottom, left = self.box
        for points in simulated_landmarks(self.box).values():
            for x, y in points:
                self.assertTrue(left <= x <= right and top <= y <= bottom, (x, y))


class DetectTests(unittest.TestCase):
    def setUp(self):
        self.engine = SimulatedFaceEngine()
        self.frame = np.zeros((120, 160, 3), np.uint8)

    def test_landmarks_only_when_asked_for(self):
        self.assertIsNone(self.engine.detect(self.frame)[0].landmarks)
        self.assertEqual(set(self.engine.detect(self.frame, landmarks=True)[0].landmarks), FEATURES)


if __name__ == "__main__":
    unittest.main()
